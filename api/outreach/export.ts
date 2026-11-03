import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin } from '../_lib/supabase';

/**
 * Exports campaign leads as JSON (for manual use or import into any LinkedIn tool).
 * This is the fallback when HeyReach isn't configured.
 *
 * Also works as a campaign status/detail endpoint.
 */
export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'GET' && req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const campaign_id = req.query.campaign_id as string || req.body?.campaign_id;
  if (!campaign_id) return res.status(400).json({ error: 'campaign_id is required' });

  try {
    const supabase = getSupabaseAdmin();

    // Get campaign
    const { data: campaign } = await supabase
      .from('outreach_campaigns')
      .select('*')
      .eq('id', campaign_id)
      .single();

    if (!campaign) return res.status(404).json({ error: 'Campaign not found' });

    // Get leads
    const { data: leads } = await supabase
      .from('outreach_leads')
      .select('*')
      .eq('campaign_id', campaign_id)
      .order('created_at');

    // Build stats
    const stats = {
      total: leads?.length || 0,
      by_step: {} as Record<string, number>,
      by_seniority: {} as Record<string, number>,
      replied: 0,
      meetings_booked: 0,
    };

    for (const lead of leads || []) {
      stats.by_step[lead.current_step] = (stats.by_step[lead.current_step] || 0) + 1;
      if (lead.seniority_level) {
        stats.by_seniority[lead.seniority_level] = (stats.by_seniority[lead.seniority_level] || 0) + 1;
      }
      if (lead.replied_at) stats.replied++;
      if (lead.meeting_booked_at) stats.meetings_booked++;
    }

    return res.status(200).json({
      campaign: {
        id: campaign.id,
        name: campaign.name,
        status: campaign.status,
        channel: campaign.channel,
        heyreach_campaign_id: campaign.heyreach_campaign_id,
        created_at: campaign.created_at,
      },
      stats,
      leads: (leads || []).map(lead => ({
        id: lead.id,
        full_name: lead.full_name,
        title: lead.title,
        company: lead.company,
        linkedin_url: lead.linkedin_url,
        email: lead.email,
        seniority_level: lead.seniority_level,
        relevance_context: lead.personalization_context,
        messages: {
          connection_note: lead.connection_note,
          follow_up_1: lead.follow_up_1,
          follow_up_2: lead.follow_up_2,
          follow_up_3: lead.follow_up_3,
          inmail: lead.inmail_message,
        },
        status: {
          current_step: lead.current_step,
          connection_sent_at: lead.connection_sent_at,
          connection_accepted_at: lead.connection_accepted_at,
          replied_at: lead.replied_at,
          reply_sentiment: lead.reply_sentiment,
          meeting_booked_at: lead.meeting_booked_at,
          opted_out: lead.opted_out,
        },
      })),
    });

  } catch (error: any) {
    console.error('Error exporting campaign:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
}
