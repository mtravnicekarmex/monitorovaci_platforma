import requests
from typing import Dict
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


GATEWAY_BASE = "http://192.168.88.250:8080"
SEND_ENDPOINT = f"http://192.168.88.250:8080/send-sms"



def send_sms(phone: str, message: str, timeout: float = 10.0) -> Dict:
    payload = {"phone": phone, "message": message}


    try:
        r = requests.post(SEND_ENDPOINT, json=payload, timeout=timeout)
        r.raise_for_status()
        print("Sent successfully")
        return r.json()

    except requests.exceptions.ConnectTimeout:
        error_msg = f"Connection to gateway {GATEWAY_BASE} timed out. Is the device online?"
        logger.error(error_msg)
        return {"error": "timeout", "message": error_msg}

    except requests.exceptions.ConnectionError:
        error_msg = f"Failed to connect to {GATEWAY_BASE}. Check if the service is running."
        logger.error(error_msg)
        return {"error": "connection_failed", "message": error_msg}

    except requests.exceptions.HTTPError as e:
        logger.error(f"Gateway returned an error: {e}")
        return {"error": "http_error", "status_code": r.status_code, "text": r.text}

    except ValueError:
        # Handles cases where response is not valid JSON
        return {"status_code": r.status_code, "text": r.text}

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return {"error": "unexpected_error", "details": str(e)}

