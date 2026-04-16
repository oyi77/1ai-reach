import { NextRequest, NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import fs from "fs/promises";

const execAsync = promisify(exec);

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file") as File;
    const waNumberId = formData.get("wa_number_id") as string;

    if (!file || !waNumberId) {
      return NextResponse.json(
        { error: "File and wa_number_id required" },
        { status: 400 }
      );
    }

    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);
    const tempPath = `/tmp/kb_import_${Date.now()}_${file.name}`;
    await fs.writeFile(tempPath, buffer);

    const { stdout, stderr } = await execAsync(
      `python3 scripts/kb_import_export.py import "${tempPath}" --wa-number-id "${waNumberId}"`,
      { cwd: "/home/openclaw/.openclaw/workspace/1ai-reach", timeout: 30000 }
    );

    await fs.unlink(tempPath);

    if (stderr && !stdout) {
      return NextResponse.json({ error: stderr }, { status: 500 });
    }

    const match = stdout.match(/Imported (\d+) KB entries/);
    const count = match ? parseInt(match[1]) : 0;

    return NextResponse.json({
      success: true,
      count,
      message: stdout.trim(),
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Import failed" },
      { status: 500 }
    );
  }
}
