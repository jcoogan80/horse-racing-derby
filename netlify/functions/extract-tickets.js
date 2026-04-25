// Netlify serverless function — extracts exotic wager tickets from a screenshot
// Called by the Today's Card "Import Tickets from Screenshot" feature.
// Requires ANTHROPIC_API_KEY set in Netlify environment variables (Site Settings → Env vars).
// Node 18+ required for built-in fetch — enforced via netlify.toml NODE_VERSION.

exports.handler = async function (event) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'ANTHROPIC_API_KEY not configured on server.' })
    };
  }

  let body;
  try {
    body = JSON.parse(event.body);
  } catch {
    return {
      statusCode: 400,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'Invalid JSON body.' })
    };
  }

  const { image, mimeType } = body;
  if (!image || !mimeType) {
    return {
      statusCode: 400,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'Missing image or mimeType.' })
    };
  }

  const prompt = `You are analyzing a horse racing ticket screenshot. Extract every exotic wager ticket combination visible in the image.

For each ticket, produce an object with two keys:
- "ticket": the combination string — horses within a leg separated by commas, legs separated by forward slashes
- "base": the wager base amount as a number (e.g. 0.50, 0.20, 1.00, 2.00). Look for a dollar amount printed on the ticket such as "$0.50", "$.50", "$0.20", "$2.00". If you cannot find a base amount, use null.

Rules for the ticket string:
- Use only the program numbers printed on the ticket
- Each "/" moves to the next race/leg; multiple horses in the same leg are separated by commas
- Do NOT include wager type names, race labels, or dollar amounts inside the ticket string itself

Return ONLY a valid JSON array of these objects and nothing else.
Example response: [{"ticket":"7,8/1,7/3,5/2,3/3,7","base":0.50},{"ticket":"1/2,3/4/5,6/7","base":0.50}]
If no tickets are visible, return: []`;

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1024,
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'image',
                source: { type: 'base64', media_type: mimeType, data: image }
              },
              { type: 'text', text: prompt }
            ]
          }
        ]
      })
    });

    if (!response.ok) {
      const errText = await response.text();
      return {
        statusCode: 502,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error: 'Anthropic API error.', detail: errText })
      };
    }

    const data = await response.json();
    const rawText = (data.content[0].text || '').trim();

    // Strip markdown code fences if the model wrapped the JSON
    const cleaned = rawText.replace(/^```[a-z]*\n?/i, '').replace(/\n?```$/i, '').trim();
    const parsed  = JSON.parse(cleaned);

    // Normalize: handle plain strings in case the model ignores the new format
    const tickets = Array.isArray(parsed) ? parsed.map(t =>
      typeof t === 'string' ? { ticket: t, base: null } : t
    ) : [];

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickets })
    };
  } catch (err) {
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'Failed to process image.', detail: err.message })
    };
  }
};
