"""Entrada do WhatsApp: JID interno (@lid) e roteamento depois que a mensagem já foi gravada."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.channels.inbound_sync import _poll_jids
from app.channels.tasks import continue_after_inbound, conversation_for_phone
from app.channels.whatsapp import _contact_jid, inbound_from_record
from app.models.enums import ConversationState, Intent


def test_poll_jids_keeps_lid_and_phone():
    jids = _poll_jids({
        "remoteJid": "271751305011249@lid",
        "lastMessage": {
            "key": {
                "remoteJid": "271751305011249@lid",
                "remoteJidAlt": "5511988887777@s.whatsapp.net",
                "fromMe": False,
            }
        },
    })
    assert "271751305011249@lid" in jids
    assert "5511988887777@s.whatsapp.net" in jids


def test_contact_jid_prefers_phone_over_lid():
    assert _contact_jid({
        "remoteJid": "123456@lid",
        "remoteJidAlt": "5511988887777@s.whatsapp.net",
    }) == "5511988887777@s.whatsapp.net"


def test_inbound_from_document_receipt():
    msg = inbound_from_record("Cobranca", {
        "key": {
            "id": "DOC1",
            "fromMe": False,
            "remoteJid": "123@lid",
            "remoteJidAlt": "5511988887777@s.whatsapp.net",
        },
        "messageType": "documentMessage",
        "message": {"documentMessage": {"mimetype": "image/png", "fileName": "pix.png"}},
        "messageTimestamp": 1_700_000_000,
    })
    assert msg is not None
    assert msg.has_media
    assert msg.mimetype == "image/png"
    assert msg.phone == "5511988887777"
    assert not msg.text


def test_inbound_keeps_quoted_stanza_from_reply():
    msg = inbound_from_record("Cobranca", {
        "key": {
            "id": "IN1",
            "fromMe": False,
            "remoteJid": "271751305011249@lid",
            "remoteJidAlt": "5511952313944@s.whatsapp.net",
        },
        "message": {"conversation": "Faltam quantas parcelas?"},
        "contextInfo": {
            "stanzaId": "3EB0D9391AC54874350998",
            "quotedMessage": {"conversation": "Olá, Carla!"},
        },
        "messageTimestamp": 1_700_000_000,
    })
    assert msg is not None
    assert msg.quoted_id == "3EB0D9391AC54874350998"
    assert msg.text == "Faltam quantas parcelas?"
    assert msg.phone == "5511952313944"


def test_inbound_quoted_stanza_inside_extended_text():
    msg = inbound_from_record("Cobranca", {
        "key": {"id": "IN2", "fromMe": False, "remoteJid": "5511988887777@s.whatsapp.net"},
        "message": {
            "extendedTextMessage": {
                "text": "e as parcelas?",
                "contextInfo": {"stanzaId": "OUT9"},
            }
        },
        "messageTimestamp": 1_700_000_000,
    })
    assert msg is not None
    assert msg.quoted_id == "OUT9"
    assert msg.text == "e as parcelas?"


def test_inbound_from_find_messages_record():
    msg = inbound_from_record("Cobranca", {
        "key": {"id": "ABC", "fromMe": False, "remoteJid": "5511988887777@s.whatsapp.net"},
        "message": {"conversation": "Sim, consigo"},
        "messageTimestamp": 1_700_000_000,
        "pushName": "Maria",
    })
    assert msg is not None
    assert msg.text == "Sim, consigo"
    assert msg.phone == "5511988887777"
    assert not msg.from_me


def test_conversation_for_phone_prefers_identity_wait():
    now = datetime.now(timezone.utc)
    maria = SimpleNamespace(id=uuid4())
    carla = SimpleNamespace(id=uuid4())
    conv_maria = SimpleNamespace(
        debtor_id=maria.id, state=ConversationState.HUMANO, updated_at=now
    )
    conv_carla = SimpleNamespace(
        debtor_id=carla.id, state=ConversationState.AGUARDANDO_IDENTIDADE, updated_at=now
    )
    session = MagicMock()
    session.scalars.side_effect = [
        iter([maria, carla]),
        iter([conv_maria, conv_carla]),
    ]
    picked = conversation_for_phone(session, uuid4(), "5511952313944")
    assert picked is conv_carla


def test_continue_after_inbound_stays_quiet_when_human_owns_chat():
    conv = SimpleNamespace(state=ConversationState.HUMANO, id=uuid4(), intent=None)
    outcome, turn = continue_after_inbound(MagicMock(), MagicMock(), MagicMock(), conv, "oi")
    assert outcome == "sem_texto_ou_humano"
    assert turn is None


def test_continue_after_inbound_hands_off_to_agent(monkeypatch):
    conv = SimpleNamespace(state=ConversationState.AGENTE, id=uuid4(), intent=None)

    monkeypatch.setattr(
        "app.channels.tasks.classify_intent",
        lambda text, today: SimpleNamespace(intent=Intent.PARCELAR_DESCONTO, promised_date=None),
    )
    monkeypatch.setattr("app.channels.tasks._route_deterministic", lambda *a: None)

    tenant = SimpleNamespace(timezone="America/Sao_Paulo")
    outcome, turn = continue_after_inbound(MagicMock(), tenant, MagicMock(), conv, "qual o valor?")
    assert outcome == "agente"
    assert turn == (str(conv.id), "qual o valor?", Intent.PARCELAR_DESCONTO)
    assert conv.intent == Intent.PARCELAR_DESCONTO
    assert isinstance(date.today(), date)
