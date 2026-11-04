"""Processos independentes: gateway, cobrança, conciliação e cadastro.

O Postgres é compartilhado. Baixa, status do título e auditoria acontecem na
mesma transação, então esses serviços não se chamam por HTTP para escrever.
O que cruza a fronteira é trabalho assíncrono, na fila do serviço dono.
"""
