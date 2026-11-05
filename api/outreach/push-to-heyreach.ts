import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin } from '../_lib/supabase';
import { withAdmin } from '../_lib/auth';

/**
 * Pushes a campaign's leads to HeyReach for automated sending.
 * Creates a HeyReach campaign, adds leads with personalized messages,
 * and activates the sequence.
 *
 * Requires HEYREACH_API_KEY env var.
 */

const HEYREACH_API = 'https://api.heyreach.io/api/v1';

async function heyreachFetch(path: string, options: RequestInit = {}) {
  const apiKey = process.env.HEYREACH_API_KEY;
  if (!apiKey) throw new Error('HEYREACH_API_KEY not configured');

  const res = await fetch(`${HEYREACH_API}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-KEY': apiKey,
      ...options.headers,
    },
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`HeyReach API error ${res.status}: ${errText}`);
  }

  return res.json();
}

async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { campaign_id, linkedin_account_id } = req.body;
  if (!campaign_id) return res.status(400).json({ error: 'campaign_id is required' });

  if (!process.env.HEYREACH_API_KEY) {
    return res.status(400).json({
      error: 'HeyReach not configured',
      message: 'Add HEYREACH_API_KEY to your environment variables. Sign up at heyreach.io to get an API key.',
      manual_mode: true,
      instructions: 'Without HeyReach, you can export the outreach leads and messages from /api/outreach/export and use them manually or with any LinkedIn tool.',
    });
  }

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
      .is('heyreach_lead_id', null);

    if (!leads?.length) return res.status(200).json({ message: 'No new leads to push' });

    // Step 1: Create a lead list in HeyReach
    const list = await heyreachFetch('/lead-lists', {
      method: 'POST',
      body: JSON.stringify({
        name: campaign.name,
      }),
    });

    // Step 2: Add leads to the list
    const heyreachLeads = leads.map(lead => ({
      linkedInUrl: lead.linkedin_url,
      firstName: lead.full_name.split(' ')[0],
      lastName: lead.full_name.split(' ').slice(1).join(' '),
      company: lead.company || '',
      title: lead.title || '',
      email: lead.email || '',
      customFields: {
        connection_note: lead.connection_note,
        follow_up_1: lead.follow_up_1,
        follow_up_2: lead.follow_up_2,
        follow_up_3: lead.follow_up_3,
        inmail_message: lead.inmail_message,
      },
    }));

    const addResult = await heyreachFetch(`/lead-lists/${list.id}/leads`, {
      method: 'POST',
      body: JSON.stringify({ leads: heyreachLeads }),
    });

    // Step 3: Create a campaign with the sequence
    const heyreachCampaign = await heyreachFetch('/campaigns', {
      method: 'POST',
      body: JSON.stringify({
        name: campaign.name,
        leadListIds: [list.id],
        senderAccountIds: linkedin_account_id ? [linkedin_account_id] : undefined,
        steps: [
          {
            type: 'SEND_CONNECTION_REQUEST',
            message: '{{connection_note}}',
            delayDays: 0,
          },
          {
            type: 'SEND_MESSAGE',
            message: '{{follow_up_1}}',
            delayDays: 3,
            condition: 'CONNECTED',
          },
          {
            type: 'SEND_MESSAGE',
            message: '{{follow_up_2}}',
            delayDays: 5,
            condition: 'NO_REPLY',
          },
          {
            type: 'SEND_MESSAGE',
            message: '{{follow_up_3}}',
            delayDays: 7,
            condition: 'NO_REPLY',
          },
        ],
        settings: {
          dailyLimit: campaign.daily_limit || 30,
        },
      }),
    });

    // Step 4: Update our records with HeyReach IDs
    await supabase
      .from('outreach_campaigns')
      .update({
        heyreach_campaign_id: heyreachCampaign.id,
        heyreach_list_id: list.id,
        status: 'active',
        updated_at: new Date().toISOString(),
      })
      .eq('id', campaign_id);

    // Update leads with HeyReach IDs (if returned)
    if (addResult.leads) {
      for (const hrLead of addResult.leads) {
        await supabase
          .from('outreach_leads')
          .update({ heyreach_lead_id: hrLead.id })
          .eq('campaign_id', campaign_id)
          .eq('linkedin_url', hrLead.linkedInUrl);
      }
    }

    return res.status(200).json({
      campaign_id,
      heyreach_campaign_id: heyreachCampaign.id,
      heyreach_list_id: list.id,
      leads_pushed: leads.length,
      status: 'active',
    });

  } catch (error: any) {
    console.error('Error pushing to HeyReach:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
}

export default withAdmin(handler);
