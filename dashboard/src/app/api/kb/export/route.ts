import { NextRequest, NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import fs from "fs/promises";

const execAsync = promisify(exec);

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const waNumberId = searchParams.get("wa_number_id");
  const format = searchParams.get("format") || "json";

  if (!waNumberId) {
    return NextResponse.json(
      { error: "wa_number_id required" },
      { status: 400 }
    );
  }

  try {
    const tempPath = `/tmp/kb_export_${Date.now()}.${format}`;

    await execAsync(
      `python3 scripts/kb_import_export.py export "${tempPath}" --wa-number-id "${waNumberId}" --format ${format}`,
      { cwd: "/home/openclaw/.openclaw/workspace/1ai-reach", timeout: 30000 }
    );

    const fileContent = await fs.readFile(tempPath);
    await fs.unlink(tempPath);

    const contentTypes: Record<string, string> = {
      json: "application/json",
      csv: "text/csv",
      markdown: "text/markdown",
      text: "text/plain",
    };

    return new NextResponse(fileContent, {
      headers: {
        "Content-Type": contentTypes[format] || "application/octet-stream",
        "Content-Disposition": `attachment; filename="kb_export_${waNumberId}.${format}"`,
      },
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Export failed" },
      { status: 500 }
    );
  }
}
