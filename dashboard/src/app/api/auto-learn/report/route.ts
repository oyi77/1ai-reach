import { NextRequest, NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const session = searchParams.get("session");

  if (!session) {
    return NextResponse.json({ error: "Session required" }, { status: 400 });
  }

  try {
    const { stdout, stderr } = await execAsync(
      `python3 scripts/cs_learn.py report --wa-number-id "${session}"`,
      { cwd: "/home/openclaw/.openclaw/workspace/1ai-reach", timeout: 30000 }
    );

    if (stderr) {
      console.error("Report stderr:", stderr);
    }

    return NextResponse.json({
      success: true,
      output: stdout,
      funnel_summary: {},
      winning_patterns: [],
      low_performers: [],
      suggested_entries: [],
    });
  } catch (error) {
    console.error("Report generation error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Report generation failed" },
      { status: 500 }
    );
  }
}
