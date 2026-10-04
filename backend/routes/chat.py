"""Groq-powered chatbot endpoint."""

import os

import requests
from flask import Blueprint, current_app, jsonify, request

chat_bp = Blueprint("chat", __name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"
MAX_MESSAGE_LENGTH = 4000

SYSTEM_PROMPT = (
    "You are GovEase Assistant, an AI assistant for the GovEase application. "
    "Help users understand Indian government services, schemes, public "
    "information, and how to navigate GovEase. Give clear, concise and "
    "practical answers. Do not invent official eligibility requirements or "
    "government facts. If you are uncertain, clearly say so. You do not have "
    "access to live government records or the GovEase news database; advise "
    "users to confirm important details with the relevant official source."
)


@chat_bp.route("/chat", methods=["POST"])
def chat():
    """Return one answer from Groq for the submitted user message."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({
            "error": "invalid_request",
            "message": "Send a JSON object with a message.",
        }), 400

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({
            "error": "invalid_message",
            "message": "Enter a question to continue.",
        }), 400

    message = message.strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({
            "error": "message_too_long",
            "message": "Keep your question under 4000 characters.",
        }), 400

    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GROK_API_KEY")
    if not api_key:
        return jsonify({
            "error": "chat_unavailable",
            "message": "The chatbot is not configured. Set GROQ_API_KEY in the project .env file.",
        }), 503

    try:
        response = requests.post(
            GROQ_CHAT_URL,
            headers={"Authorization": "Bearer " + api_key},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                "temperature": 0.4,
                "max_tokens": 700,
            },
            timeout=(5, 30),
        )
        response.raise_for_status()
        data = response.json()
    except requests.Timeout:
        current_app.logger.warning("Groq chatbot request timed out")
        return jsonify({
            "error": "chat_timeout",
            "message": "The chatbot took too long to respond. Please try again.",
        }), 504
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None
        current_app.logger.warning("Groq chatbot returned HTTP %s", status_code)
        if status_code == 429:
            return jsonify({
                "error": "chat_busy",
                "message": "The AI service is busy. Please try again shortly.",
            }), 503
        return jsonify({
            "error": "chat_upstream_error",
            "message": "The AI service could not complete your request.",
        }), 502
    except requests.RequestException as error:
        current_app.logger.error(
            "Groq chatbot network request failed (%s)", type(error).__name__
        )
        return jsonify({
            "error": "chat_upstream_error",
            "message": "Could not reach the AI service. Please try again.",
        }), 502
    except ValueError:
        current_app.logger.error("Groq chatbot returned invalid JSON")
        return jsonify({
            "error": "chat_upstream_error",
            "message": "The AI service returned an invalid response.",
        }), 502

    choices = data.get("choices") if isinstance(data, dict) else None
    answer = None
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            answer_message = first_choice.get("message")
            if isinstance(answer_message, dict):
                answer = answer_message.get("content")

    if not isinstance(answer, str) or not answer.strip():
        current_app.logger.error("Groq chatbot response did not contain an answer")
        return jsonify({
            "error": "chat_upstream_error",
            "message": "The AI service returned an empty response. Please try again.",
        }), 502

    return jsonify({"response": answer.strip()})
