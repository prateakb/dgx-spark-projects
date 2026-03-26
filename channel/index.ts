import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { ZulipClient } from "./zulip-client.js";
import { Allowlist } from "./allowlist.js";

const allowlist = new Allowlist(process.env.ALLOWLIST_FILE ?? "/data/allowlist.json");
const zulip = new ZulipClient({
  url: process.env.ZULIP_URL!,
  email: process.env.ZULIP_EMAIL!,
  apiKey: process.env.ZULIP_API_KEY!,
});

const server = new McpServer({
  name: "zulip-channel",
  version: "0.1.0",
  capabilities: {
    "claude/channel": {}, // registers this as a push channel, not just a tool server
    tools: {},
  },
  instructions: `
    You receive messages from Zulip. Each event has: sender_email, stream, topic, content.
    Use the reply tool to respond to the same stream and topic.
    Only act on messages from allowlisted senders.
    If a sender is unknown, respond with a pairing code and wait for confirmation.
  `,
});

// Tool Claude calls to send a reply back to Zulip
server.tool(
  "reply",
  {
    content: z.string().describe("Message to send back to Zulip"),
    stream: z.string().describe("Zulip stream name"),
    topic: z.string().describe("Zulip topic"),
  },
  async ({ content, stream, topic }) => {
    await zulip.sendMessage({ type: "stream", to: stream, topic, content });
    return { content: [{ type: "text", text: "sent" }] };
  }
);

// Tool to confirm a pairing code from the terminal
server.tool(
  "confirm_pairing",
  {
    code: z.string().describe("The pairing code to confirm"),
  },
  async ({ code }) => {
    const email = allowlist.confirmPairing(code);
    if (!email) {
      return { content: [{ type: "text", text: `Invalid or expired pairing code: ${code}` }] };
    }
    return { content: [{ type: "text", text: `Paired successfully: ${email} is now allowlisted` }] };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);

// Long-poll Zulip event queue and push into Claude's session
let lastEventId = -1;

async function startPolling() {
  const queue = await zulip.registerEventQueue(["message"]);

  if (!queue.queue_id) {
    console.error("Failed to register Zulip event queue:", queue);
    process.exit(1);
  }

  console.error(`[zulip-channel] Registered event queue: ${queue.queue_id}`);
  console.error(`[zulip-channel] Listening for messages...`);

  while (true) {
    try {
      const events = await zulip.getEvents(queue.queue_id, lastEventId);

      for (const event of events) {
        lastEventId = event.id;
        if (event.type !== "message") continue;

        const msg = event.message;
        const senderEmail: string = msg.sender_email;
        const stream: string =
          typeof msg.display_recipient === "string"
            ? msg.display_recipient
            : msg.display_recipient?.[0]?.full_name ?? "unknown";
        const topic: string = msg.subject ?? msg.topic ?? "general";
        const content: string = msg.content;

        // Skip messages from the bot itself
        if (senderEmail === process.env.ZULIP_EMAIL) continue;

        if (!allowlist.has(senderEmail)) {
          // Pairing flow: unknown sender gets a one-time code
          const code = allowlist.generatePairingCode(senderEmail);
          await zulip.sendMessage({
            type: "stream",
            to: stream,
            topic,
            content: `Pairing required. Run in the Claude Code terminal:\n\`/zulip:access pair ${code}\``,
          });
          continue;
        }

        // Push the event into Claude's running session
        await server.notification("channel/message", {
          sender: senderEmail,
          stream,
          topic,
          content,
        });
      }
    } catch (err) {
      console.error("[zulip-channel] Polling error:", err);
      // Wait before retrying to avoid tight error loops
      await new Promise((resolve) => setTimeout(resolve, 5000));
    }
  }
}

startPolling();
