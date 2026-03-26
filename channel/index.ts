import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { ZulipClient } from "./zulip-client.js";
import { Allowlist } from "./allowlist.js";

const allowlist = new Allowlist(process.env.ALLOWLIST_FILE ?? "/data/allowlist.json");
const zulip = new ZulipClient({
  url: process.env.ZULIP_URL!,
  email: process.env.ZULIP_EMAIL!,
  apiKey: process.env.ZULIP_API_KEY!,
});

const server = new Server(
  { name: "zulip", version: "0.1.0" },
  {
    capabilities: {
      experimental: {
        "claude/channel": {},
      },
      tools: {},
    },
    instructions: `
      You receive messages from Zulip. Each event has: sender_email, stream, topic, content.
      Use the reply tool to respond to the same stream and topic.
      Only act on messages from allowlisted senders.
      If a sender is unknown, respond with a pairing code and wait for confirmation.
    `,
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "reply",
      description: "Send a message back to a Zulip stream/topic",
      inputSchema: {
        type: "object" as const,
        properties: {
          content: { type: "string", description: "Message to send back to Zulip" },
          stream: { type: "string", description: "Zulip stream name" },
          topic: { type: "string", description: "Zulip topic" },
        },
        required: ["content", "stream", "topic"],
      },
    },
    {
      name: "confirm_pairing",
      description: "Confirm a pairing code to allowlist a Zulip sender",
      inputSchema: {
        type: "object" as const,
        properties: {
          code: { type: "string", description: "The pairing code to confirm" },
        },
        required: ["code"],
      },
    },
  ],
}));

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  if (name === "reply") {
    const { content, stream, topic } = args as { content: string; stream: string; topic: string };
    await zulip.sendMessage({ type: "stream", to: stream, topic, content });
    return { content: [{ type: "text", text: "sent" }] };
  }

  if (name === "confirm_pairing") {
    const { code } = args as { code: string };
    const email = allowlist.confirmPairing(code);
    if (!email) {
      return { content: [{ type: "text", text: `Invalid or expired pairing code: ${code}` }] };
    }
    return { content: [{ type: "text", text: `Paired successfully: ${email} is now allowlisted` }] };
  }

  return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
});

// Connect transport
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
          const code = allowlist.generatePairingCode(senderEmail);
          await zulip.sendMessage({
            type: "stream",
            to: stream,
            topic,
            content: `Pairing required. Run in the Claude Code terminal:\n\`/zulip:access pair ${code}\``,
          });
          continue;
        }

        // Push the event into Claude's running session via channel notification
        await server.notification({
          method: "notifications/claude/channel",
          params: {
            content: content,
            meta: {
              sender: senderEmail,
              stream,
              topic,
            },
          },
        });
      }
    } catch (err) {
      console.error("[zulip-channel] Polling error:", err);
      await new Promise((resolve) => setTimeout(resolve, 5000));
    }
  }
}

startPolling();
