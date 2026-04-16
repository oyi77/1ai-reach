import { NextRequest, NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { session, apply } = body;

  if (!session) {
    return NextResponse.json({ error: "Session required" }, { status: 400 });
  }

  try {
    const cmd = apply
      ? `python3 scripts/cs_learn.py improve --wa-number-id "${session}" --apply`
      : `python3 scripts/cs_learn.py improve --wa-number-id "${session}"`;

    const { stdout, stderr } = await execAsync(cmd, {
      cwd: "/home/openclaw/.openclaw/workspace/1ai-reach",
      timeout: 30000,
    });

    if (stderr) {
      console.error("Improve stderr:", stderr);
    }

    return NextResponse.json({
      success: true,
      output: stdout,
      patterns_added: 0,
      suggestions_created: 0,
      errors: [],
    });
  } catch (error) {
    console.error("Auto-improvement error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Auto-improvement failed" },
      { status: 500 }
    );
  }
}
