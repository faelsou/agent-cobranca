"""Filas de cada serviço. O worker só escuta as suas; a rota manda a task para o dono."""

from fnmatch import fnmatch

# Nome da task → fila. Chave exata ganha do glob.
TASK_ROUTES: dict[str, dict[str, str]] = {
    "app.channels.tasks.process_inbound": {"queue": "cobranca-llm"},
    "app.agent.*": {"queue": "cobranca-llm"},
    "app.dunning.*": {"queue": "cobranca"},
    "app.receipts.*": {"queue": "conciliacao-llm"},
    "app.reconciliation.*": {"queue": "conciliacao"},
    "app.ingest.*": {"queue": "cadastro"},
}

# Argumento -Q de cada worker. Tem de cobrir toda fila que TASK_ROUTES entrega a ele.
WORKER_QUEUES: dict[str, tuple[str, ...]] = {
    "cobranca": ("cobranca", "cobranca-llm"),
    "conciliacao": ("conciliacao", "conciliacao-llm"),
    "cadastro": ("cadastro",),
}


def queue_for(task_name: str) -> str:
    exact = TASK_ROUTES.get(task_name)
    if exact is not None:
        return exact["queue"]
    for pattern, dest in TASK_ROUTES.items():
        if fnmatch(task_name, pattern):
            return dest["queue"]
    raise KeyError(task_name)
