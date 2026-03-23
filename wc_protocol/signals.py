"""WeeChat signal name constants for inter-plugin communication.

These signal names form the contract between weechat-zenoh and weechat-agent.
Centralizing them here prevents silent breakage from typos or renames.
"""

SIGNAL_MESSAGE_SENT = "zenoh_message_sent"
SIGNAL_MESSAGE_RECEIVED = "zenoh_message_received"
SIGNAL_PRESENCE_CHANGED = "zenoh_presence_changed"
