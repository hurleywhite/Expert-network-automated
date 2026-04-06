import type { VercelRequest, VercelResponse } from '@vercel/node';
import Anthropic from '@anthropic-ai/sdk';
import { getSupabaseAdmin } from '../lib/supabase';

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { project_id, min_relevance_score = 0, limit = 20, sender_name = 'Hurley' } = req.body;
  if (!project_id) return res.status(400).json({ error: 'project_id is required' });

  try {
    const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const supabase = getSupabaseAdmin();

    // Get project info
    const { data: project } = await supabase
      .from('project_briefs')
      .select('*')
      .eq('id', project_id)
      .single();

    if (!project) return res.status(404).json({ error: 'Project not found' });

    // Get expert profiles with candidates that have LinkedIn URLs and no existing outreach
    const { data: profiles } = await supabase
      .from('expert_profiles')
      .select(`
        id,
        ai_overview,
        project_expertise,
        relevance_score,
        candidates!inner (
          full_name,
          title,
          company,
          linkedin_url
        )
      `)
      .eq('project_id', project_id)
      .gte('relevance_score', min_relevance_score)
      .not('candidates.linkedin_url', 'is', null)
      .limit(limit);

    if (!profiles?.length) {
      return res.status(200).json({ project_id, generated: 0, message: 'No eligible experts found' });
    }

    // Filter out ones that already have linkedin outreach
    const profileIds = profiles.map((p: any) => p.id);
    const { data: existingOutreach } = await supabase
      .from('linkedin_outreach')
      .select('expert_profile_id')
      .in('expert_profile_id', profileIds);

    const existingIds = new Set((existingOutreach || []).map((o: any) => o.expert_profile_id));
    const newProfiles = profiles.filter((p: any) => !existingIds.has(p.id));

    let generated = 0;

    for (const profile of newProfiles) {
      const candidate = (profile as any).candidates;

      // Generate personalized connection note (max 300 chars)
      const message = await anthropic.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 512,
        messages: [{
          role: 'user',
          content: `Write a LinkedIn connection request note for an expert network outreach. Keep it under 280 characters.

From: ${sender_name} at ArcticBlue AI
To: ${candidate.full_name}, ${candidate.title} at ${candidate.company}
Project Context: ${project.name} (${project.industry || 'research project'})
Expert Relevance: ${(profile as any).project_expertise?.slice(0, 2).join('; ') || 'domain expert'}

Rules:
- Be professional but warm, not salesy
- Mention a specific reason for connecting (their expertise area)
- Keep under 280 characters
- Don't use generic phrases like "I came across your profile"
- End with a soft ask (brief chat, share perspectives)

Return ONLY the connection note text, no quotes or formatting.`
        }]
      });

      const connectionNote = (message.content[0].type === 'text' ? message.content[0].text : '').trim().substring(0, 300);

      // Generate follow-up message
      const followUpMsg = await anthropic.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1024,
        messages: [{
          role: 'user',
          content: `Write a LinkedIn follow-up message after connecting. This is for an expert network — we want to schedule a paid consultation call.

From: ${sender_name} at ArcticBlue AI
To: ${candidate.full_name}, ${candidate.title} at ${candidate.company}
Project: ${project.name}
Their Expertise: ${(profile as any).project_expertise?.join('; ') || 'relevant domain knowledge'}

Rules:
- Professional, concise (3-4 sentences max)
- Explain the expert network opportunity briefly
- Mention it's a paid consultation (typical rates $200-500/hr)
- Ask for a brief 15-min intro call
- Don't be pushy

Return ONLY the message text, no quotes.`
        }]
      });

      const followUpMessage = followUpMsg.content[0].type === 'text' ? followUpMsg.content[0].text.trim() : '';

      // Insert the outreach record
      await supabase.from('linkedin_outreach').insert({
        expert_profile_id: (profile as any).id,
        linkedin_url: candidate.linkedin_url,
        connection_note: connectionNote,
        follow_up_message: followUpMessage,
        status: 'pending',
      });

      // Log activity
      await supabase.from('expert_activities').insert({
        expert_profile_id: (profile as any).id,
        activity_type: 'linkedin_sent',
        description: 'LinkedIn outreach message generated',
      });

      generated++;
    }

    return res.status(200).json({
      project_id,
      generated,
      skipped_existing: existingIds.size,
    });

  } catch (error: any) {
    console.error('Error generating LinkedIn outreach:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
}
