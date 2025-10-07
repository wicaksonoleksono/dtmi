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


async def send_wablas_message(recipient_phone: str, message_text: str) -> bool:
    api_key = current_app.config.get("WABLASS_API_KEY")
    secret_key = current_app.config.get("WABLASS_WEBHOOK_SECRET")
    logger.info(f"Sending message to: {recipient_phone}")
    logger.info(f"Message preview: {message_text[:100]}...")
    logger.debug(f"API Key present: {bool(api_key)}")
    logger.debug(f"Secret present: {bool(secret_key)}")

    if not api_key or not secret_key:
        logger.error("WABLASS_API_KEY or WABLASS_WEBHOOK_SECRET not configured")
        return False
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
                return True
            logger.error(f"Failed - HTTP {resp.status_code}, Data: {data}")
            logger.error(f"Wablas send failed HTTP {resp.status_code}: {data or resp.text[:300]}")
            return False

    except httpx.TimeoutException:
        logger.error("Wablas send timeout")
        return False
    except httpx.HTTPError as e:
        logger.error(f"Wablas HTTP error: {e}")
        return False


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
        await send_wablas_message(target_phone, "Maaf, terjadi kesalahan di server kami. Silakan coba lagi nanti.")
        return jsonify({'error': 'Internal server error'}), 500

    print(f"[WEBHOOK DEBUG] Generated answer: {answer[:100]}...")
    print(f"[WEBHOOK DEBUG] Sending reply to: {target_phone}")

    sent = await send_wablas_message(target_phone, answer)
    print(f"[WEBHOOK DEBUG] Message sent result: {sent}")

    if not sent:
        print("[WEBHOOK DEBUG] Failed to send message!")
        print("[WEBHOOK DEBUG] Reply not sent; check device status or token/secret")

    return jsonify({'status': 'success', 'message': 'Processed successfully'})