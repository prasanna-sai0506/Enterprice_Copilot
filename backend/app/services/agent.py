from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
from plotly import graph_objects as go
from plotly.utils import PlotlyJSONEncoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import SalesRecord
from ..schemas import ChatResponse, ChartPayload, Citation
from .knowledge import KnowledgeBase, SearchHit


@dataclass
class ToolResult:
    name: str
    payload: Any


class EnterpriseCopilot:
    def __init__(self) -> None:
        self.knowledge = KnowledgeBase()

    def answer(self, db: Session, user_role: str, query: str, conversation_id: int | None = None) -> ChatResponse:
        normalized = query.lower().strip()
        tool_used: list[str] = []
        citations: list[Citation] = []
        answer_parts: list[str] = []
        chart: ChartPayload | None = None

        rag_hits = self.knowledge.search(db, query)
        if rag_hits:
            tool_used.append("rag_tool")
            citations.extend(self._citations_from_hits(rag_hits))

        if self._needs_summary(normalized):
            tool_used.append("summary_tool")
            if rag_hits:
                answer_parts.append(self._summarize_hits(rag_hits, line_limit=10 if "10" in normalized else 6))
            else:
                answer_parts.append("I could not find enough document content to summarize. Please upload the document first.")
        elif self._needs_document_sales_analytics(normalized) and rag_hits:
            analysis = self._analyze_uploaded_sales_document(db, rag_hits, normalized)
            if analysis:
                tool_used.append("document_analytics_tool")
                answer_parts.append(analysis["summary"])
                if analysis.get("chart_data"):
                    tool_used.append("chart_tool")
                    chart = self._chart_payload(analysis["chart_data"], title=analysis["chart_title"])
            else:
                tool_used.append("document_analytics_tool")
                answer_parts.append("I found the uploaded sales report, but I could not reliably parse the month-by-month figures. Try asking for a summary instead.")
        elif self._needs_analytics(normalized):
            tool_used.append("sql_tool")
            table = self._run_sales_analytics(db, normalized)
            answer_parts.append(table["summary"])
            if table.get("chart_data"):
                tool_used.append("chart_tool")
                chart = self._chart_payload(table["chart_data"], title=table["chart_title"])
        elif self._needs_forecast(normalized):
            tool_used.append("forecast_tool")
            forecast = self._forecast_sales(db)
            answer_parts.append(forecast["summary"])
            chart = self._chart_payload(forecast["chart_data"], title=forecast["chart_title"])
            tool_used.append("chart_tool")
        else:
            if rag_hits:
                answer_parts.append(self._rag_summary(rag_hits))
            else:
                answer_parts.append(
                    "I could not find a direct match in uploaded documents or demo data. Try asking about sales trends, forecasts, or upload a document to query it."
                )

        if not answer_parts:
            answer_parts.append("No answer could be generated.")

        return ChatResponse(
            conversation_id=conversation_id or 1,
            answer="\n\n".join(answer_parts),
            citations=citations,
            chart=chart,
            tool_used=tool_used or ["assistant"],
        )

    def _needs_analytics(self, query: str) -> bool:
        triggers = ["sales", "revenue", "orders", "profit", "region", "month", "quarter", "trend", "breakdown", "why did"]
        return any(trigger in query for trigger in triggers)

    def _needs_forecast(self, query: str) -> bool:
        triggers = ["forecast", "predict", "next quarter", "next month", "future", "will look like"]
        return any(trigger in query for trigger in triggers)

    def _needs_summary(self, query: str) -> bool:
        triggers = ["summarize", "summarise", "summary", "in 10 lines", "in ten lines", "short summary", "brief summary"]
        return any(trigger in query for trigger in triggers)

    def _needs_document_sales_analytics(self, query: str) -> bool:
        triggers = [
            "past 2 months",
            "last 2 months",
            "past few months",
            "last few months",
            "recent months",
            "sales report",
            "dashboard analytics",
            "month by month",
        ]
        return any(trigger in query for trigger in triggers)

    def _run_sales_analytics(self, db: Session, query: str) -> dict[str, Any]:
        rows = db.scalars(select(SalesRecord).order_by(SalesRecord.period, SalesRecord.region, SalesRecord.product)).all()
        frame = pd.DataFrame([{"period": row.period, "region": row.region, "product": row.product, "revenue": row.revenue, "orders": row.orders, "profit": row.profit} for row in rows])
        if frame.empty:
            return {"summary": "No sales data is available.", "chart_data": None}

        if "region" in query:
            grouped = frame.groupby("region", as_index=False)[["revenue", "orders", "profit"]].sum()
            top_row = grouped.sort_values("revenue", ascending=False).iloc[0]
            summary = f"Revenue is strongest in {top_row['region']} at ${top_row['revenue']:,.0f}."
            chart_data = grouped.to_dict(orient="records")
            return {"summary": summary, "chart_title": "Revenue by Region", "chart_data": chart_data}

        monthly = frame.groupby("period", as_index=False)[["revenue", "orders", "profit"]].sum().sort_values("period")
        delta = monthly["revenue"].diff().fillna(0)
        latest = monthly.iloc[-1]
        previous = monthly.iloc[-2] if len(monthly) > 1 else latest
        summary = (
            f"Latest period {latest['period']} generated ${latest['revenue']:,.0f} in revenue and {int(latest['orders'])} orders. "
            f"Revenue changed by ${latest['revenue'] - previous['revenue']:,.0f} versus the prior period."
        )
        return {"summary": summary, "chart_title": "Monthly Revenue Trend", "chart_data": monthly.to_dict(orient="records")}

    def _forecast_sales(self, db: Session) -> dict[str, Any]:
        rows = db.scalars(select(SalesRecord).order_by(SalesRecord.period)).all()
        frame = pd.DataFrame([{"period": row.period, "revenue": row.revenue} for row in rows])
        monthly = frame.groupby("period", as_index=False)["revenue"].sum().sort_values("period")
        if len(monthly) < 2:
            return {"summary": "Not enough sales history to forecast.", "chart_data": None}

        x = pd.RangeIndex(start=0, stop=len(monthly))
        y = monthly["revenue"].astype(float)
        slope = (y.iloc[-1] - y.iloc[0]) / max(len(y) - 1, 1)
        intercept = y.iloc[0]
        predictions = []
        for step in range(1, 4):
            index = len(monthly) - 1 + step
            predicted = intercept + slope * index
            lower = predicted * 0.92
            upper = predicted * 1.08
            predictions.append({"period": f"forecast-{step}", "revenue": round(predicted, 2), "lower": round(lower, 2), "upper": round(upper, 2)})
        summary = f"A simple trend forecast expects next-quarter revenue around ${predictions[0]['revenue']:,.0f} and rising into the following months."
        chart_data = monthly.to_dict(orient="records") + predictions
        return {"summary": summary, "chart_title": "Revenue Forecast", "chart_data": chart_data}

    def _chart_payload(self, rows: list[dict[str, Any]] | None, title: str) -> ChartPayload | None:
        if not rows:
            return None
        frame = pd.DataFrame(rows)
        if "region" in frame.columns:
            fig = go.Figure(data=[go.Bar(x=frame["region"], y=frame["revenue"], marker_color="#d4a373")])
        else:
            fig = go.Figure()
            if "lower" in frame.columns:
                historical = frame[~frame["period"].astype(str).str.startswith("forecast")]
                forecast = frame[frame["period"].astype(str).str.startswith("forecast")]
                fig.add_trace(go.Scatter(x=historical["period"], y=historical["revenue"], mode="lines+markers", name="History", line=dict(color="#1d3557", width=3)))
                fig.add_trace(go.Scatter(x=forecast["period"], y=forecast["revenue"], mode="lines+markers", name="Forecast", line=dict(color="#e76f51", dash="dash")))
            else:
                fig.add_trace(go.Scatter(x=frame["period"], y=frame["revenue"], mode="lines+markers", name="Revenue", line=dict(color="#1d3557", width=3)))
        fig.update_layout(template="plotly_white", title=title, height=360, margin=dict(l=24, r=24, t=56, b=24), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        safe_spec = json.loads(json.dumps(fig.to_plotly_json(), cls=PlotlyJSONEncoder))
        return ChartPayload(kind="plotly", title=title, spec=safe_spec)

    def _citations_from_hits(self, hits: list[SearchHit]) -> list[Citation]:
        return [Citation(source=hit.source, page=hit.page, excerpt=hit.excerpt) for hit in hits]

    def _rag_summary(self, hits: list[SearchHit]) -> str:
        best = hits[0]
        return f"The strongest document match comes from {best.source} (page {best.page}). It suggests: {best.excerpt}"

    def _summarize_hits(self, hits: list[SearchHit], line_limit: int = 6) -> str:
        unique_sentences: list[str] = []
        seen: set[str] = set()

        for hit in hits:
            cleaned = hit.excerpt.replace("\n", " ").strip()
            for sentence in cleaned.split(". "):
                sentence = sentence.strip()
                if len(sentence) < 18:
                    continue
                key = sentence.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique_sentences.append(sentence.rstrip("."))
                if len(unique_sentences) >= line_limit:
                    break
            if len(unique_sentences) >= line_limit:
                break

        if not unique_sentences:
            return "No clear summary could be extracted from the uploaded document."

        bullets = [f"{index + 1}. {sentence}." for index, sentence in enumerate(unique_sentences)]
        return "Here is a concise summary of the uploaded document:\n\n" + "\n".join(bullets)

    def _analyze_uploaded_sales_document(self, db: Session, hits: list[SearchHit], query: str) -> dict[str, Any] | None:
        source_name = next(
            (
                hit.source
                for hit in hits
                if any(keyword in hit.source.lower() for keyword in ["sales", "report", "monthly", "financial"])
            ),
            next((hit.source for hit in hits if hit.source.lower().endswith((".pdf", ".csv", ".docx", ".txt"))), hits[0].source),
        )
        text = self.knowledge.get_document_text(db, source_name)
        monthly_rows = self._extract_monthly_rows(text)
        if len(monthly_rows) < 2:
            return None

        window_size = 2 if any(trigger in query for trigger in ["past 2 months", "last 2 months"]) else 3
        window = monthly_rows[-window_size:]
        first = window[0]
        latest = window[-1]
        best = max(window, key=lambda row: row["revenue"])
        worst = min(window, key=lambda row: row["revenue"])
        change = latest["revenue"] - first["revenue"]
        change_direction = "increased" if change >= 0 else "decreased"

        summary = (
            f"Here is the sales dashboard summary from {source_name} for the last {len(window)} month(s). "
            f"Revenue {change_direction} from ${first['revenue']:,.0f} to ${latest['revenue']:,.0f} ({change:+,.0f}). "
            f"The latest month was {latest['period']}, with ${latest['revenue']:,.0f} revenue, {latest['orders']:,} orders, and ${latest['profit']:,.0f} profit. "
            f"Best month in this window: {best['period']} at ${best['revenue']:,.0f}; weakest month: {worst['period']} at ${worst['revenue']:,.0f}."
        )

        return {
            "summary": summary,
            "chart_title": f"{source_name} - Recent Sales Trend",
            "chart_data": [{"period": row["period"], "revenue": row["revenue"], "orders": row["orders"], "profit": row["profit"]} for row in window],
        }

    def _extract_monthly_rows(self, text: str) -> list[dict[str, Any]]:
        month_pattern = re.compile(r"^(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)$", re.IGNORECASE)
        month_order = {month: index for index, month in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
        rows: list[dict[str, Any]] = []

        lowered = text.lower()
        for marker in ["monthly revenue table", "monthly performance", "month | revenue | orders | profit"]:
            marker_index = lowered.find(marker)
            if marker_index != -1:
                text = text[marker_index:]
                break

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        pending_month: str | None = None
        pending_numbers: list[float] = []

        for line in lines:
            if line.lower() in {"month", "revenue", "orders", "profit", "margin %", "quarter", "quarterly performance", "monthly revenue table"}:
                continue

            month_match = month_pattern.fullmatch(line)
            if month_match:
                pending_month = month_match.group(1).title()[:3]
                pending_numbers = []
                continue

            if pending_month is None:
                continue

            if not re.search(r"\d", line):
                continue

            number = self._parse_number(line.replace("$", "").replace("%", ""))
            if number == 0.0 and not any(ch.isdigit() for ch in line):
                continue

            pending_numbers.append(number)
            if len(pending_numbers) >= 3:
                rows.append(
                    {
                        "period": pending_month,
                        "revenue": pending_numbers[0],
                        "orders": int(pending_numbers[1]),
                        "profit": pending_numbers[2],
                    }
                )
                pending_month = None
                pending_numbers = []

        cleaned: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row["revenue"] == 0 and row["orders"] == 0 and row["profit"] == 0:
                continue
            cleaned[row["period"]] = row

        return sorted(cleaned.values(), key=lambda row: month_order.get(row["period"], 999))

    def _parse_number(self, value: str) -> float:
        cleaned = value.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
