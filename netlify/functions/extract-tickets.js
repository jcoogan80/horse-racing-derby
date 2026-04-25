// Netlify serverless function — extracts exotic wager tickets from a screenshot
// Called by the Today's Card "Import Tickets from Screenshot" feature.
// Requires ANTHROPIC_API_KEY set in Netlify environment variables.

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

For each ticket, format it as:
- Horses within a leg separated by commas
- Legs separated by forward slashes

Example: 7,8/1,7/3,5/2,3/3,7

Rules:
- Use only the program numbers (the numbers printed on the ticket)
- Each "/" represents moving to the next race/leg
- Multiple horses in the same leg are listed with commas between them
- Do NOT include the wager type name, dollar amount, or race labels — only the horse numbers

Return ONLY a valid JSON array of ticket strings and nothing else.
Example response: ["7,8/1,7/3,5/2,3/3,7","1/2,3/4/5,6/7"]
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
    const tickets = JSON.parse(cleaned);

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickets: Array.isArray(tickets) ? tickets : [] })
    };
  } catch (err) {
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'Failed to process image.', detail: err.message })
    };
  }
};
