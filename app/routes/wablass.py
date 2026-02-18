import httpx
import logging
from flask import Blueprint, request, jsonify, current_app
from ..service import WablassService

# Configure logger to write to optima.log
logger = logging.getLogger('wablass')
logger.setLevel(logging.INFO)
handler = logging.FileHandler('optima.log')
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

wablas_bp = Blueprint('wablas_bp', __name__)


async def send_wablas_message(recipient_phone: str, message_text: str) -> tuple[bool, str]:
    """Send a message via Wablas API.

    Returns:
        tuple of (success: bool, detail: str) — detail contains the actual error on failure.
    """
    api_key = current_app.config.get("WABLASS_API_KEY")
    secret_key = current_app.config.get("WABLASS_WEBHOOK_SECRET")
    logger.info(f"Sending message to: {recipient_phone}")
    logger.info(f"Message preview: {message_text[:100]}...")

    if not api_key or not secret_key:
        missing = []
        if not api_key:
            missing.append("WABLASS_API_KEY")
        if not secret_key:
            missing.append("WABLASS_WEBHOOK_SECRET")
        err = f"Missing config: {', '.join(missing)}"
        logger.error(err)
        return False, err

    api_url = 'https://sby.wablas.com/api/send-message'
    headers = {'Authorization': f"{api_key}.{secret_key}"}
    payload = {'phone': recipient_phone, 'message': message_text}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(api_url, headers=headers, json=payload)
            data = {}
            try:
                data = resp.json()
                logger.info(f"Response JSON: {data}")
            except Exception as e:
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Non-JSON response from Wablas: {resp.text[:300]}")
            if resp.is_success and data.get('status') == 'success':
                logger.info("Message sent successfully!")
                return True, "OK"
            err = f"HTTP {resp.status_code} — {data or resp.text[:300]}"
            logger.error(f"Wablas send failed: {err}")
            return False, err

    except httpx.TimeoutException:
        err = "Timeout after 15s connecting to Wablas API"
        logger.error(err)
        return False, err
    except httpx.HTTPError as e:
        err = f"HTTP error: {e}"
        logger.error(err)
        return False, err
    except Exception as e:
        err = f"Unexpected error: {e}"
        logger.error(err)
        return False, err


@wablas_bp.route('/webhook', methods=['POST'])
async def webhook_endpoint():
    logger.info("Webhook called!")
    data = request.get_json(silent=True) or {}
    logger.info(f"Received data: {data}")

    if data.get('isFromMe'):
        logger.info("Skipped self-sent message")
        return jsonify({'status': 'success', 'message': 'Skipped self-sent message'})

    user_message = (data.get('message') or '').strip()
    target_phone = data.get('phone')  # per docs: phone = sender/customer number

    if not user_message or not target_phone:
        logger.warning("Missing fields: message or phone")
        return jsonify({'error': 'Missing required fields: message and phone'}), 400

    try:
        service = WablassService(
            static_dir=current_app.static_folder,
            vectorstore=current_app.vector_db,
            llm=current_app.agent,
            wablass_agent=current_app.wablass_agent,
            router_agent=current_app.router_agent,
        )
        # Just await; DO NOT mess with the event loop
        result = await service.generate_answer(
            query=user_message,
            query_types="all",
            year="SARJANA",
            top_k=8,
            context_expansion_window=3,
            session_id=f"wablass_{target_phone}",
        )
        answer = result.get('answer') or "Maaf, saya tidak dapat menemukan jawaban."
    except Exception as e:
        print(f"[WEBHOOK DEBUG] Error generating answer: {e}")
        sent, detail = await send_wablas_message(target_phone, "Maaf, terjadi kesalahan di server kami. Silakan coba lagi nanti.")
        if not sent:
            print(f"[WEBHOOK DEBUG] Also failed to send error message: {detail}")
        return jsonify({'error': 'Internal server error'}), 500

    print(f"[WEBHOOK DEBUG] Generated answer: {answer[:100]}...")
    print(f"[WEBHOOK DEBUG] Sending reply to: {target_phone}")

    sent, detail = await send_wablas_message(target_phone, answer)

    if sent:
        print(f"[WEBHOOK DEBUG] Message sent successfully")
    else:
        print(f"[WEBHOOK DEBUG] FAILED to send message → {detail}")

    return jsonify({'status': 'success', 'message': 'Processed successfully'})