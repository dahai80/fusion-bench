import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/db";
import { benchmarks } from "@/db/schema";
import { eq } from "drizzle-orm";

function safeJsonParse(raw: string | null | undefined): unknown {
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const numericId = parseInt(id, 10);
        if (Number.isNaN(numericId)) {
            return NextResponse.json({ detail: "Invalid id" }, { status: 400 });
        }
        const db = getDb();
        const row = db.select().from(benchmarks).where(eq(benchmarks.id, numericId)).get();

        if (!row) {
            return NextResponse.json({ detail: "Not found" }, { status: 404 });
        }

        return NextResponse.json({
            ...row,
            batching_results: safeJsonParse(row.batchingResults),
            detail: safeJsonParse(row.detail),
        });
    } catch (e: unknown) {
        
        console.error("API error:", e); return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
    }
}
