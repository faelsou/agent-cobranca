"""Até cinco WhatsApps por devedor."""

import pytest
from pydantic import ValidationError

from app.core.phones import merge_phones, normalize_phone_list
from app.ingest.schemas import InvoiceIn
from app.ingest.service import parse_invoice_csv


def test_normaliza_celular_com_mascara_e_ddi():
    assert normalize_phone_list(["(11) 98888-7777"]) == ["5511988887777"]
    assert normalize_phone_list(["5511988887777"]) == ["5511988887777"]


def test_aceita_varios_na_mesma_celula_e_deduplica():
    assert normalize_phone_list(["11988887777 | 11977776666 / 11988887777"]) == [
        "5511988887777",
        "5511977776666",
    ]


def test_rejeita_mais_de_cinco():
    numeros = [f"1198888777{i}" for i in range(6)]
    with pytest.raises(ValueError, match="5"):
        normalize_phone_list(numeros)


def test_rejeita_telefone_invalido():
    with pytest.raises(ValueError, match="inválido"):
        normalize_phone_list(["falar com a Ana"])


def test_planilha_le_colunas_extras():
    csv = (
        "referencia,nome,documento,telefone,telefone2,email,valor,vencimento\n"
        "NF-1,Padaria,12345678000190,11988887777,21977776666,a@b.com,10.00,15/04/2026\n"
    )
    rows, errors = parse_invoice_csv(csv.encode())
    assert errors == []
    assert rows[0].debtor_phones == ["5511988887777", "5521977776666"]
    assert rows[0].debtor_phone == "5511988887777"


def test_titulo_recusa_sexto_numero():
    with pytest.raises(ValidationError):
        InvoiceIn(
            external_id="NF-1",
            debtor_name="Padaria",
            debtor_document="12345678000190",
            debtor_phones=[f"1198888777{i}" for i in range(6)],
            amount="10.00",
            due_date="2026-04-15",
        )


def test_reimportar_troca_o_principal_e_guarda_os_extras():
    assert merge_phones("5511988887777", ["5511988887777", "5511977776666"], ["5511966665555"]) == [
        "5511966665555",
        "5511977776666",
    ]


def test_reimportar_sem_telefone_nao_apaga():
    atual = ["5511988887777", "5511977776666"]
    assert merge_phones(atual[0], atual, []) == atual
