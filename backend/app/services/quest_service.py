import json
import logging
import socket
import threading
import time
from typing import Optional

from app.state import State


class QuestService:
    """Service class to manage the Quest connection and state."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def announce_to_quest(
        self,
        local_ip: str,
        local_port: int,
        quest_ip: str,
        quest_port: int,
        retries: int = 3,
    ) -> bool:
        """Announce the local IP and port to the Quest."""
        message = {
            "ip": local_ip,
            "port": local_port,
        }
        udp_msg = json.dumps(message).encode("utf-8")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                ok = False
                for _ in range(retries):
                    try:
                        sock.sendto(udp_msg, (quest_ip, quest_port))
                        ok = True
                        logging.info(f"Announced to Quest at {quest_ip}:{quest_port}")
                        break
                    except socket.error as e:
                        logging.error(f"Failed to send announcement: {e}")
                        time.sleep(1)
                if not ok:
                    logging.error("Failed to announce to Quest after retries")
                    return False
        except Exception as e:
            logging.error(f"Error in announce_to_quest: {e}")
            return False
        return True

    def start_udp_listener(self, local_ip: str, local_port: int):
        """Start a UDP listener for the Quest."""
        if self._thread and self._thread.is_alive():
            if State.quest_udp_bind == (local_ip, local_port):
                logging.info(
                    "UDP listener is already running on the specified address."
                )
                return True
            self.stop_udp_listener()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._udp_listener, args=(local_ip, local_port), daemon=True
        )
        self._thread.start()
        State.quest_udp_bind = (local_ip, local_port)
        logging.info(f"Started UDP listener on {local_ip}:{local_port}")
        return True

    def stop_udp_listener(self):
        """Stop the UDP listener."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join()
        State.quest_udp_running = False
        State.quest_udp_bind = None
        logging.info("Stopped UDP listener")

    def _udp_listener(self, local_ip: str, local_port: int):
        State.quest_udp_running = True

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((local_ip, local_port))
                sock.settimeout(1.0)
                logging.info(f"UDP listener bound to {local_ip}:{local_port}")
                while not self._stop_event.is_set():
                    try:
                        data, addr = sock.recvfrom(1024)
                        udp_msg = data.decode("utf-8")
                        payload = json.loads(udp_msg)
                        if "timestamp" not in payload:
                            payload["timestamp"] = time.time()
                        State.quest_seq += 1
                        payload["_server_seq"] = State.quest_seq
                        State.quest_state = payload
                        logging.debug(f"Received UDP message: {payload}")
                    except socket.timeout:
                        continue
                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to decode JSON from UDP message: {e}")
                    except Exception as e:
                        logging.error(f"Error in UDP listener: {e}")
        finally:
            State.quest_udp_running = False
            State.quest_udp_bind = None
            logging.info("UDP listener thread exiting")


quest_service = QuestService()
