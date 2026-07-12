# ADR-0009: Loop de polling in-process em vez de agendador externo

## Status
Aceito

## Contexto
O monitoramento contínuo precisa repetir a varredura em intervalos regulares. Isso poderia ser feito por um agendador externo (cron, Task Scheduler do Windows) disparando `python main.py --once` repetidamente, ou por um loop dentro do próprio processo Python.

## Decisão
`main()` implementa um loop `while True` com `time.sleep(config.monitor.check_interval_seconds)` entre execuções de `run_scan`, quando `--once` não é passado (`main.py`). O processo permanece de pé indefinidamente até `Ctrl+C`.

## Consequências
**Positivas**
- Zero dependência de infraestrutura de agendamento do SO — roda com `python main.py` em qualquer máquina com Chrome instalado, inclusive interativamente.
- Estado do processo (browser, sessão) pode em tese ser reaproveitado entre ciclos (embora hoje `browser.quit()` feche tudo a cada ciclo via `finally`).
- Mais simples de raciocinar para um usuário único rodando localmente.

**Negativas / trade-offs**
- Sem supervisão de processo (systemd, Task Scheduler, container restart policy), uma falha não tratada que escape do `try/except` de `run_scan` derruba o loop inteiro sem retomada automática.
- Não há distribuição de carga nem paralelismo — é inerentemente um processo único, sequencial.
- Alterar o intervalo de checagem exige reiniciar o processo (não há reload de configuração em tempo de execução).

## Alternativas consideradas
- **Cron / Agendador de Tarefas do Windows** chamando `--once` a cada ciclo: mais resiliente a falhas individuais (cada execução é isolada) e mais fácil de supervisionar externamente, mas exige configuração fora do repositório (registro no agendador do SO) e não foi adotado para manter o projeto autocontido e simples de rodar com um único comando.
