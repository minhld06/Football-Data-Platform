import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

import chat_engine
import openrouter_client
import queries
from db import get_chatbot_connection, get_connection
from rate_limit import enforce_chat_rate_limit
from schemas import ChatModelInfo, ChatRequest, ChatResponse

router = APIRouter()
logger = logging.getLogger(__name__)

DEFAULT_ROW_LIMIT = 100


def _fetch_team_alias_rows(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sa.alias, tp.team_id, tp.team_name
            FROM gold.search_aliases sa
            JOIN gold.team_profile tp ON tp.team_id = sa.entity_id
            WHERE sa.entity_type = 'team'
            """
        )
        return cur.fetchall()


def _log_chat(conn, *, conversation_id, message, model, sql, answer, prompt_tokens, completion_tokens, latency_ms, cost_estimate):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chatbot.chat_logs
                (conversation_id, user_message, model, sql_generated, response, prompt_tokens, completion_tokens, latency_ms, cost_estimate_usd)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (conversation_id, message, model, sql, answer, prompt_tokens, completion_tokens, latency_ms, cost_estimate),
        )
    conn.commit()


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    pricing = openrouter_client.get_model_catalog().get(model)
    if pricing is None:
        return None
    prompt_cost = (prompt_tokens / 1_000_000) * (pricing.get("prompt_price_per_million") or 0)
    completion_cost = (completion_tokens / 1_000_000) * (pricing.get("completion_price_per_million") or 0)
    return round(prompt_cost + completion_cost, 6)


@router.get("/models", response_model=list[ChatModelInfo])
def list_models():
    catalog = openrouter_client.get_model_catalog()
    return [
        ChatModelInfo(
            id=model_id,
            label=label,
            context_window=catalog.get(model_id, {}).get("context_window"),
            prompt_price_per_million=catalog.get(model_id, {}).get("prompt_price_per_million"),
            completion_price_per_million=catalog.get(model_id, {}).get("completion_price_per_million"),
        )
        for model_id, label in chat_engine.ALLOWED_MODELS.items()
    ]


@router.post("", response_model=ChatResponse, dependencies=[Depends(enforce_chat_rate_limit)])
def chat(request: ChatRequest):
    if request.model not in chat_engine.ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unsupported model: {request.model}")

    conversation_id = request.conversation_id or str(uuid.uuid4())
    prompt_tokens = 0
    completion_tokens = 0
    latency_ms = 0

    with get_connection() as log_conn:
        if chat_engine.looks_like_injection(request.message):
            refusal = "Sorry, I can only answer football questions on this platform."
            _log_chat(
                log_conn, conversation_id=conversation_id, message=request.message, model=request.model,
                sql=None, answer=refusal, prompt_tokens=0, completion_tokens=0, latency_ms=0, cost_estimate=0,
            )
            return ChatResponse(conversation_id=conversation_id, answer=refusal, sql=None)

        resolved_teams: list[dict] = []
        try:
            with get_chatbot_connection() as alias_conn:
                alias_rows = _fetch_team_alias_rows(alias_conn)
            resolved_teams = queries.resolve_team_mentions(request.message, alias_rows)
        except Exception:
            # Team-nickname resolution is a prompt enrichment, not the core
            # query path (which has its own error handling below) — a lookup
            # failure here should degrade to an unresolved prompt, not fail
            # the whole request.
            logger.warning("Team alias lookup failed; continuing without resolved teams", exc_info=True)

        intent = chat_engine.classify_intent(request.message)

        try:
            sql_call = openrouter_client.call_chat_completion(
                request.model,
                [
                    {"role": "system", "content": chat_engine.build_system_prompt(resolved_teams, intent)},
                    {"role": "user", "content": request.message},
                ],
            )
        except openrouter_client.OpenRouterError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        prompt_tokens += sql_call["prompt_tokens"]
        completion_tokens += sql_call["completion_tokens"]
        latency_ms += sql_call["latency_ms"]

        raw_sql = chat_engine.extract_sql(sql_call["content"])
        if raw_sql is None:
            answer = sql_call["content"].strip()
            _log_chat(
                log_conn, conversation_id=conversation_id, message=request.message, model=request.model,
                sql=None, answer=answer, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                latency_ms=latency_ms, cost_estimate=_estimate_cost(request.model, prompt_tokens, completion_tokens),
            )
            return ChatResponse(conversation_id=conversation_id, answer=answer, sql=None)

        try:
            safe_sql = chat_engine.validate_sql(raw_sql, default_limit=DEFAULT_ROW_LIMIT)
        except chat_engine.SqlValidationError:
            refusal = "Sorry, I cannot generate a valid query for this question, please try asking in a different way."
            _log_chat(
                log_conn, conversation_id=conversation_id, message=request.message, model=request.model,
                sql=raw_sql, answer=refusal, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                latency_ms=latency_ms, cost_estimate=_estimate_cost(request.model, prompt_tokens, completion_tokens),
            )
            return ChatResponse(conversation_id=conversation_id, answer=refusal, sql=raw_sql)

        try:
            with get_chatbot_connection() as chat_conn, chat_conn.cursor() as cur:
                cur.execute(safe_sql)
                rows = cur.fetchall()
        except Exception:
            refusal = "Sorry, there was an error with the data query, please try asking in a different way."
            _log_chat(
                log_conn, conversation_id=conversation_id, message=request.message, model=request.model,
                sql=safe_sql, answer=refusal, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                latency_ms=latency_ms, cost_estimate=_estimate_cost(request.model, prompt_tokens, completion_tokens),
            )
            return ChatResponse(conversation_id=conversation_id, answer=refusal, sql=safe_sql)

        try:
            answer_call = openrouter_client.call_chat_completion(
                request.model,
                [{"role": "user", "content": chat_engine.build_answer_prompt(request.message, rows, DEFAULT_ROW_LIMIT)}],
            )
        except openrouter_client.OpenRouterError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        prompt_tokens += answer_call["prompt_tokens"]
        completion_tokens += answer_call["completion_tokens"]
        latency_ms += answer_call["latency_ms"]

        _log_chat(
            log_conn, conversation_id=conversation_id, message=request.message, model=request.model,
            sql=safe_sql, answer=answer_call["content"], prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            latency_ms=latency_ms, cost_estimate=_estimate_cost(request.model, prompt_tokens, completion_tokens),
        )
        return ChatResponse(conversation_id=conversation_id, answer=answer_call["content"], sql=safe_sql)