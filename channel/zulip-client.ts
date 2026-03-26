export interface ZulipClientConfig {
  url: string;
  email: string;
  apiKey: string;
}

export interface ZulipMessage {
  type: string;
  to: string;
  topic: string;
  content: string;
}

export class ZulipClient {
  private base: string;
  private auth: string;

  constructor({ url, email, apiKey }: ZulipClientConfig) {
    this.base = `${url}/api/v1`;
    this.auth = Buffer.from(`${email}:${apiKey}`).toString("base64");
  }

  private async fetch(path: string, opts: RequestInit = {}): Promise<any> {
    const res = await fetch(`${this.base}${path}`, {
      ...opts,
      headers: {
        Authorization: `Basic ${this.auth}`,
        ...opts.headers,
      },
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Zulip API error ${res.status}: ${text}`);
    }

    return res.json();
  }

  async registerEventQueue(eventTypes: string[]): Promise<{ queue_id: string; last_event_id: number }> {
    const body = new URLSearchParams({
      event_types: JSON.stringify(eventTypes),
    });
    return this.fetch("/register", { method: "POST", body });
  }

  async getEvents(queueId: string, lastEventId: number): Promise<any[]> {
    const params = new URLSearchParams({
      queue_id: queueId,
      last_event_id: String(lastEventId),
      dont_block: "false", // long-poll — blocks until new events arrive
    });
    const data = await this.fetch(`/events?${params}`);
    return data.events ?? [];
  }

  async sendMessage(msg: ZulipMessage): Promise<any> {
    const body = new URLSearchParams(msg as Record<string, string>);
    return this.fetch("/messages", { method: "POST", body });
  }

  async getMessageById(messageId: number): Promise<any> {
    return this.fetch(`/messages/${messageId}`);
  }
}
