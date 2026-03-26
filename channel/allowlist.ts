import fs from "fs";
import crypto from "crypto";

interface AllowlistData {
  allowed: string[];
  pending: Record<string, string>; // code -> email
}

export class Allowlist {
  private path: string;
  private data: AllowlistData;

  constructor(path: string) {
    this.path = path;
    this.data = fs.existsSync(path)
      ? JSON.parse(fs.readFileSync(path, "utf8"))
      : { allowed: [], pending: {} };
  }

  has(email: string): boolean {
    return this.data.allowed.includes(email);
  }

  generatePairingCode(email: string): string {
    const code = crypto.randomBytes(4).toString("hex").toUpperCase();
    this.data.pending[code] = email;
    this.save();
    return code;
  }

  confirmPairing(code: string): string | false {
    const email = this.data.pending[code];
    if (!email) return false;
    if (!this.data.allowed.includes(email)) {
      this.data.allowed.push(email);
    }
    delete this.data.pending[code];
    this.save();
    return email;
  }

  listAllowed(): string[] {
    return [...this.data.allowed];
  }

  removeAllowed(email: string): boolean {
    const idx = this.data.allowed.indexOf(email);
    if (idx === -1) return false;
    this.data.allowed.splice(idx, 1);
    this.save();
    return true;
  }

  private save(): void {
    const dir = this.path.substring(0, this.path.lastIndexOf("/"));
    if (dir && !fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(this.path, JSON.stringify(this.data, null, 2));
  }
}
