"""Provider adapters for sending original admission documents to AI APIs.

This module owns only provider-specific transport. Prompt/schema/mapping/normalization
remain in extraction.py. Native PDF input is used where the API supports it; for
OpenAI-compatible gateways, PDFs are rendered as images only when that generic API
has no guaranteed native-PDF contract.
"""
from __future__ import annotations
import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx
import pymupdf

SYSTEM_INSTRUCTION = "Follow the system rules exactly. Return only the requested structured JSON. Never fabricate missing information."


def _file_data(path: Path, max_pages: int) -> tuple[str, str, int, bytes]:
    if not path.is_file():
        raise FileNotFoundError("Original document file was not found.")
    ext = path.suffix.lower()
    raw = path.read_bytes()
    if not raw:
        raise ValueError("The document file is empty.")
    if ext == ".pdf":
        try:
            with pymupdf.open(path) as pdf:
                if pdf.is_encrypted:
                    raise ValueError("Password-protected PDFs are not supported.")
                pages = len(pdf)
                if pages < 1:
                    raise ValueError("The PDF contains no pages.")
                if pages > max_pages:
                    raise ValueError(f"PDF has {pages} pages; configured limit is {max_pages}.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("The uploaded PDF could not be opened.") from exc
        return "application/pdf", "pdf", pages, raw
    if ext in {".jpg", ".jpeg", ".png"}:
        return ("image/png" if ext == ".png" else "image/jpeg"), "image", 1, raw
    raise ValueError("Only PDF, JPG, JPEG and PNG files are accepted.")


def _raise_for_response(response: httpx.Response, provider: str, model: str) -> None:
    if response.status_code in {401, 403}:
        raise RuntimeError(f"{provider} authentication failed. Check the API key and account access.")
    if response.status_code == 404:
        raise RuntimeError(f"Configured model '{model}' was not found or is unavailable on {provider}.")
    if response.status_code == 402:
        raise RuntimeError(f"{provider} rejected the request because of account/credit limits.")
    if response.status_code == 400:
        raise RuntimeError(f"{provider} rejected the request format or model capability: {response.text[:700]}")
    response.raise_for_status()


def _post(url: str, headers: dict[str, str], payload: dict[str, Any], settings: Any) -> dict[str, Any]:
    response = None
    for attempt in range(settings.max_retries + 1):
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=settings.request_timeout_seconds)
            if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < settings.max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            _raise_for_response(response, settings.provider, settings.model)
            return response.json()
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt >= settings.max_retries:
                raise RuntimeError(f"Could not reach {settings.provider} after retrying.") from None
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError("AI provider returned no response.")


def _chat_content(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("AI provider returned an unexpected chat-completions response structure.") from exc
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    usage = data.get("usage") or {}
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI provider returned an empty response.")
    return content, {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}


def request_document(settings: Any, file_path: str | Path, prompt: str, max_pages: int) -> dict[str, Any]:
    """Send one original document and return {content, usage, page_count}.

    The same prompt is used for all providers. Provider differences are isolated here.
    """
    path = Path(file_path)
    mime, kind, page_count, raw = _file_data(path, max_pages)
    encoded = base64.b64encode(raw).decode("ascii")
    provider = settings.provider

    if provider == "gemini":
        # Request JSON output; canonical keys and value types are validated downstream.
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [
                {"text": prompt}, {"inlineData": {"mimeType": mime, "data": encoded}}
            ]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        url = f"{settings.base_url}/models/{settings.model}:generateContent"
        headers = {"x-goog-api-key": settings.api_key, "Content-Type": "application/json"}
        data = _post(url, headers, payload, settings)
        try:
            content = "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"] if isinstance(part, dict))
        except (KeyError, IndexError, TypeError) as exc:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            if reason:
                raise ValueError(f"Gemini did not process the document (block reason: {reason}).") from exc
            raise ValueError("Gemini returned an unexpected response structure.") from exc
        usage = data.get("usageMetadata") or {}
        usage = {"input_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount")}

    elif provider == "openai":
        # Responses API supports native PDF file input and image input.
        if kind == "pdf":
            document = {"type": "input_file", "filename": path.name, "file_data": f"data:application/pdf;base64,{encoded}"}
        else:
            document = {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"}
        payload = {
            "model": settings.model,
            "instructions": SYSTEM_INSTRUCTION,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}, document]}],
            "temperature": 0,
            "text": {"format": {"type": "json_object"}},
        }
        url = f"{settings.base_url}/responses"
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        data = _post(url, headers, payload, settings)
        content = data.get("output_text", "")
        if not content:
            texts = []
            for item in data.get("output", []):
                for part in item.get("content", []):
                    if part.get("type") in {"output_text", "text"}:
                        texts.append(part.get("text", ""))
            content = "".join(texts)
        usage_data = data.get("usage") or {}
        usage = {"input_tokens": usage_data.get("input_tokens"), "output_tokens": usage_data.get("output_tokens")}

    elif provider == "claude":
        # Anthropic Messages API: original PDFs use a document block; images use image blocks.
        if kind == "pdf":
            document = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": encoded}}
        else:
            document = {"type": "image", "source": {"type": "base64", "media_type": mime, "data": encoded}}
        payload = {
            "model": settings.model, "max_tokens": 12000, "temperature": 0,
            "system": SYSTEM_INSTRUCTION,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, document]}],
        }
        url = f"{settings.base_url}/messages"
        headers = {"x-api-key": settings.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        data = _post(url, headers, payload, settings)
        content = "".join(part.get("text", "") for part in data.get("content", []) if isinstance(part, dict))
        usage_data = data.get("usage") or {}
        usage = {"input_tokens": usage_data.get("input_tokens"), "output_tokens": usage_data.get("output_tokens")}

    elif provider == "mistral":
        part = ({"type": "document_url", "document_url": f"data:application/pdf;base64,{encoded}"}
                if kind == "pdf" else {"type": "image_url", "image_url": f"data:{mime};base64,{encoded}"})
        payload = {"model": settings.model, "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": [{"type": "text", "text": prompt}, part]},
        ], "temperature": 0, "response_format": {"type": "json_object"}}
        url = f"{settings.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        data = _post(url, headers, payload, settings)
        content, usage = _chat_content(data)

    else:
        # OpenRouter and custom OpenAI-compatible APIs use chat-completions.
        # Native PDF contracts differ, so PDF pages are rendered as images here only.
        if kind == "pdf":
            image_parts = []
            try:
                with pymupdf.open(path) as pdf:
                    for page in pdf:
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False)
                        image = base64.b64encode(pix.tobytes("png")).decode("ascii")
                        image_parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}})
            except Exception as exc:
                raise ValueError("The PDF could not be rendered for this OpenAI-compatible vision API.") from exc
        else:
            image_parts = [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}]
        payload = {"model": settings.model, "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": [{"type": "text", "text": prompt}, *image_parts]},
        ], "temperature": 0, "response_format": {"type": "json_object"}}
        url = f"{settings.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers.update({"HTTP-Referer": "http://localhost", "X-Title": "Narissa Admission Form Digitization"})
        data = _post(url, headers, payload, settings)
        content, usage = _chat_content(data)

    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{provider} returned an empty response. The selected model may not support this input or request format.")
    return {"content": content, "usage": usage, "page_count": page_count}
