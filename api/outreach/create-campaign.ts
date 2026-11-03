import type { VercelRequest, VercelResponse } from '@vercel/node';
import Anthropic from '@anthropic-ai/sdk';
import { getSupabaseAdmin } from '../_lib/supabase';

/**
 * Creates an outreach campaign for a project:
 * 1. Selects qualified experts (by relevance score + seniority)
 * 2. Uses Claude to generate personalized, multi-step LinkedIn sequences for each lead
 * 3. Stores everything in outreach_campaigns + outreach_leads tables
 * 4. Ready to push to HeyReach (or manual send)
 */
export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const {
    project_id,
    campaign_name,
    min_relevance_score = 50,
    limit = 25,
    max_per_company = 1,  // Company diversity: max experts per company in a campaign
    sender_name = 'Hurley',
    sender_title = 'Founder, ArcticBlue AI',
    target_seniority = ['VP', 'Director', 'C-Suite', 'Head', 'SVP', 'EVP', 'Chief', 'Partner', 'Managing Director'],
    consultation_rate = '$200-500/hr',
    call_duration = '45-60 minutes',
    context_override,  // Optional: custom project pitch to weave into messages
  } = req.body;

  if (!project_id) return res.status(400).json({ error: 'project_id is required' });

  try {
    const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const supabase = getSupabaseAdmin();

    // Get project details
    const { data: project } = await supabase
      .from('project_briefs')
      .select('*')
      .eq('id', project_id)
      .single();

    if (!project) return res.status(404).json({ error: 'Project not found' });

    // Get categories for context
    const { data: categories } = await supabase
      .from('project_categories')
      .select('name, description')
      .eq('project_id', project_id);

    // Create the campaign
    const { data: campaign, error: campError } = await supabase
      .from('outreach_campaigns')
      .insert({
        project_id,
        name: campaign_name || `${project.name} — LinkedIn Outreach`,
        channel: 'linkedin',
        status: 'draft',
        sender_name,
        sender_title,
        min_relevance_score,
        target_seniority,
      })
      .select()
      .single();

    if (campError) throw campError;

    // Get a generous pool of qualified experts with LinkedIn URLs, best first.
    // We fetch more than `limit` so we can enforce company diversity and still fill the campaign.
    const poolSize = Math.min(Math.max(limit * 10, 100), 500);
    const { data: pool } = await supabase
      .from('expert_profiles')
      .select(`
        id,
        ai_overview,
        project_expertise,
        relevance_score,
        exa_research,
        candidates!inner (
          full_name,
          title,
          company,
          linkedin_url,
          headline,
          email,
          region
        )
      `)
      .eq('project_id', project_id)
      .gte('relevance_score', min_relevance_score)
      .not('candidates.linkedin_url', 'is', null)
      .order('relevance_score', { ascending: false })
      .limit(poolSize);

    if (!pool?.length) {
      return res.status(200).json({
        campaign_id: campaign.id,
        leads_created: 0,
        message: 'No qualified experts with LinkedIn profiles found. Try lowering min_relevance_score or sourcing more experts.',
      });
    }

    // Enforce company diversity: at most `max_per_company` experts per company.
    // The pool is ordered by relevance_score desc, so we keep the strongest expert(s) per company.
    const normalizeCompany = (name: string | null | undefined): string => {
      if (!name) return '';
      return name
        .toLowerCase()
        .replace(/[.,]/g, '')
        .replace(/\b(inc|llc|ltd|limited|corp|corporation|co|company|gmbh|sa|ag|plc|group|holdings|the)\b/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    };

    const perCompanyCap = Math.max(1, Number(max_per_company) || 1);
    const companyCounts: Record<string, number> = {};
    const profiles: any[] = [];
    for (const p of pool) {
      const company = normalizeCompany((p as any).candidates?.company);
      // Candidates with an unknown company are each treated as distinct (cannot prove same employer).
      if (company) {
        const count = companyCounts[company] || 0;
        if (count >= perCompanyCap) continue;
        companyCounts[company] = count + 1;
      }
      profiles.push(p);
      if (profiles.length >= limit) break;
    }

    // Build project context for Claude
    const projectContext = context_override || `
Project: ${project.name}
Industry: ${project.industry || 'N/A'}
Focus Areas: ${(project.keywords || []).join(', ')}
Expert Categories: ${(categories || []).map((c: any) => c.name).join(', ')}
    `.trim();

    let leadsCreated = 0;

    for (const profile of profiles) {
      const candidate = (profile as any).candidates;
      const expertise = (profile as any).project_expertise || [];
      const exaResearch = (profile as any).exa_research || {};

      // Detect seniority level
      const titleLower = (candidate.title || '').toLowerCase();
      let seniority = 'Senior';
      if (/\b(ceo|cto|cfo|coo|cmo|cio|chief|founder|co-founder)\b/i.test(titleLower)) seniority = 'C-Suite';
      else if (/\b(svp|evp|senior vice president|executive vice president)\b/i.test(titleLower)) seniority = 'SVP/EVP';
      else if (/\b(vp|vice president)\b/i.test(titleLower)) seniority = 'VP';
      else if (/\b(director|head of|managing director)\b/i.test(titleLower)) seniority = 'Director';
      else if (/\b(partner|principal)\b/i.test(titleLower)) seniority = 'Partner';

      // Build research context from Exa
      const researchBullets = (exaResearch.results || [])
        .slice(0, 3)
        .map((r: any) => `- ${r.title}: ${r.snippet || ''}`.substring(0, 200))
        .join('\n');

      // Generate the full outreach sequence via Claude
      const message = await anthropic.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 3000,
        messages: [{
          role: 'user',
          content: `You are a world-class B2B outreach copywriter for an expert network (like GLG, AlphaSights, or Guidepoint). Generate a personalized LinkedIn outreach sequence for recruiting this executive as a paid expert consultant.

EXPERT PROFILE:
- Name: ${candidate.full_name}
- Title: ${candidate.title}
- Company: ${candidate.company}
- Headline: ${candidate.headline || 'N/A'}
- Location: ${candidate.region || 'N/A'}
- Seniority: ${seniority}
- Relevance Score: ${(profile as any).relevance_score}/100

AI-GENERATED EXPERTISE SUMMARY:
${expertise.slice(0, 4).join('\n')}

WEB RESEARCH:
${researchBullets || 'No additional research available'}

PROJECT CONTEXT:
${projectContext}

SENDER:
${sender_name}, ${sender_title}

OFFER:
- Paid consultation: ${consultation_rate} per hour
- Duration: ${call_duration}
- Format: Video call (Zoom)
- Topic: Sharing their expertise on ${project.name}

RULES FOR EACH MESSAGE:

1. CONNECTION REQUEST (≤280 characters, no links):
   - Reference something SPECIFIC about them (their role, company, a decision they made, an article)
   - Don't say "I came across your profile" or "I'd love to connect"
   - Be peer-to-peer, not salesy
   - End with a natural reason to connect
   - MUST be under 280 characters

2. FOLLOW-UP 1 (sent 3 days after they accept, 3-4 sentences):
   - Thank them for connecting
   - Briefly explain the expert network opportunity
   - Mention the specific topic and why THEIR perspective matters
   - Mention it's paid (${consultation_rate}/hr) — executives expect this
   - Soft ask: "Would a brief 15-minute intro call make sense?"

3. FOLLOW-UP 2 (sent 5 days after follow-up 1 if no reply, 2-3 sentences):
   - Gentle bump, don't repeat the whole pitch
   - Add a new angle or insight about why the timing matters
   - Even softer ask: "No worries if the timing isn't right — happy to circle back"

4. FOLLOW-UP 3 (final, sent 7 days after follow-up 2, 1-2 sentences):
   - Break-up message: "I don't want to be a pest"
   - Leave the door open: "If this ever becomes relevant, feel free to reach out"
   - Graceful exit

5. INMAIL (standalone message if connection not accepted, 4-5 sentences):
   - More formal than connection follow-ups
   - Lead with credibility (mention the client/project context without NDA details)
   - Clear value prop: paid consultation, specific topic, their unique perspective
   - Direct CTA: suggest a specific day/time range

Return a JSON object with exactly these fields:
{
  "connection_note": "The connection request text (≤280 chars)",
  "follow_up_1": "First follow-up after acceptance",
  "follow_up_2": "Second follow-up if no reply",
  "follow_up_3": "Final break-up message",
  "inmail_message": "Standalone InMail",
  "personalization_context": {
    "hook": "What specific thing about them you referenced",
    "angle": "Why their expertise is uniquely valuable",
    "tone": "peer-to-peer|respectful-formal|warm-casual"
  }
}`
        }]
      });

      const responseText = message.content[0].type === 'text' ? message.content[0].text : '';
      const jsonMatch = responseText.match(/\{[\s\S]*\}/);

      if (!jsonMatch) {
        console.error(`Failed to parse outreach for ${candidate.full_name}`);
        continue;
      }

      try {
        const parsed = JSON.parse(jsonMatch[0]);

        // Ensure connection note is ≤300 chars
        const connectionNote = (parsed.connection_note || '').substring(0, 300);

        // Insert the lead
        await supabase.from('outreach_leads').insert({
          campaign_id: campaign.id,
          expert_profile_id: (profile as any).id,
          full_name: candidate.full_name,
          title: candidate.title,
          company: candidate.company,
          linkedin_url: candidate.linkedin_url,
          email: candidate.email,
          seniority_level: seniority,
          connection_note: connectionNote,
          follow_up_1: parsed.follow_up_1 || '',
          follow_up_2: parsed.follow_up_2 || '',
          follow_up_3: parsed.follow_up_3 || '',
          inmail_message: parsed.inmail_message || '',
          personalization_context: parsed.personalization_context || {},
          current_step: 'connection_request',
        });

        leadsCreated++;
      } catch (parseErr) {
        console.error(`JSON parse error for ${candidate.full_name}:`, parseErr);
      }
    }

    // Update campaign stats
    await supabase
      .from('outreach_campaigns')
      .update({ total_leads: leadsCreated, updated_at: new Date().toISOString() })
      .eq('id', campaign.id);

    return res.status(201).json({
      campaign_id: campaign.id,
      campaign_name: campaign.name,
      leads_created: leadsCreated,
      leads_selected: profiles.length,
      max_per_company: perCompanyCap,
      unique_companies: Object.keys(companyCounts).length,
      qualified_pool_size: pool.length,
    });

  } catch (error: any) {
    console.error('Error creating outreach campaign:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
}
