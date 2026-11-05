"""Números de disparo da empresa."""

from types import SimpleNamespace

import pytest

from app.core.senders import apply_senders, fold_primary, listed_senders, normalize_senders


def test_normaliza_e_recusa_o_sexto():
    rows = [
        {"instance": f"loja-{i}", "number": f"1198888777{i}"}
        for i in range(5)
    ]
    assert len(normalize_senders(rows)) == 5
    with pytest.raises(ValueError, match="5"):
        normalize_senders([*rows, {"instance": "loja-9", "number": "11966665555"}])


def test_recusa_instancia_ou_numero_repetido():
    with pytest.raises(ValueError, match="instância"):
        normalize_senders([
            {"instance": "loja", "number": "11988887777"},
            {"instance": "loja", "number": "11977776666"},
        ])
    with pytest.raises(ValueError, match="número"):
        normalize_senders([
            {"instance": "loja-1", "number": "11988887777"},
            {"instance": "loja-2", "number": "(11) 98888-7777"},
        ])


def test_primeiro_dispara_e_apagar_promove_o_proximo():
    tenant = SimpleNamespace(whatsapp_senders=[], whatsapp_instance=None, whatsapp_number=None)
    apply_senders(tenant, [
        {"instance": "loja-1", "number": "5511988887777"},
        {"instance": "loja-2", "number": "5511977776666"},
    ])
    assert tenant.whatsapp_instance == "loja-1"
    assert tenant.whatsapp_number == "5511988887777"

    apply_senders(tenant, [tenant.whatsapp_senders[1]])
    assert tenant.whatsapp_instance == "loja-2"
    assert tenant.whatsapp_number == "5511977776666"
    assert listed_senders(tenant) == [{"instance": "loja-2", "number": "5511977776666"}]


def test_agencia_troca_o_principal_e_guarda_os_outros():
    tenant = SimpleNamespace(
        whatsapp_senders=[{"instance": "loja-1", "number": "5511988887777"}],
        whatsapp_instance="loja-nova",
        whatsapp_number="5511966665555",
    )
    fold_primary(tenant)
    assert tenant.whatsapp_instance == "loja-nova"
    assert [item["instance"] for item in tenant.whatsapp_senders] == ["loja-nova", "loja-1"]


def test_conta_antiga_sem_lista_ainda_mostra_o_numero():
    tenant = SimpleNamespace(
        whatsapp_senders=[],
        whatsapp_instance="Cobranca",
        whatsapp_number="5511999990000",
    )
    assert listed_senders(tenant) == [{"instance": "Cobranca", "number": "5511999990000"}]
