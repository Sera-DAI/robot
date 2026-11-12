# Agente do PC

Programa pequeno que fica rodando no Windows, lê a fila `robot-comandos` e desliga o PC quando
chega o comando `shutdown`. Só faz conexões de saída (HTTPS para o SQS): nenhuma porta é aberta.

Usa só a biblioteca padrão do Python (3.11 ou mais novo, instalado de python.org). Não há `pip install`.

## Regras de segurança

- Lista fixa de ações (hoje só `shutdown`). O texto da fila nunca vira linha de comando: a mensagem
  precisa ser exatamente `{"versao": 1, "acao": "shutdown"}`; qualquer outra coisa é apagada e ignorada.
- Comando enviado antes de o agente subir, ou há mais de 60 s, é descartado. Assim um "desligar" dito
  com o PC desligado não derruba o PC logo depois de ligar.
- A mensagem é apagada da fila antes de agir. Se não der para apagar, nada é executado.
- O desligamento avisa na tela e espera 30 s. Para cancelar: `shutdown /a`. Passado o prazo, o
  Windows fecha os programas abertos sem perguntar.
- A chave de acesso fica no Credential Manager do Windows. O log nunca registra chave, segredo nem
  corpo de resposta.

## Instalação (uma vez, depois do `sam deploy` da fase 4)

1. Crie a chave de acesso do usuário `robot-agente` (ver `infra/README.md`) e deixe o ID e o segredo
   à mão. Eles aparecem uma única vez.
2. Na pasta `agente`, rode a configuração. O segredo é digitado sem aparecer na tela:

   ```
   python -m robot_agente.configurar
   ```

   Ela grava a credencial no Credential Manager (alvo `robot-agente`) e a URL da fila em
   `%LOCALAPPDATA%\robot-agente\config.json`, fora do repositório.
3. Teste em primeiro plano, antes de agendar (Ctrl+C encerra):

   ```
   python -m robot_agente
   ```

   Acompanhe `%LOCALAPPDATA%\robot-agente\agente.log`. Deve aparecer "agente iniciado" e nenhum erro.
4. Registre a tarefa agendada. Abra um PowerShell como administrador, entre na pasta `agente`
   do repositório (o PowerShell de administrador abre em outra pasta) e rode:

   ```
   cd CAMINHO_DO_REPOSITORIO\agente
   powershell -ExecutionPolicy Bypass -File .\instalar_tarefa.ps1
   ```

   O Windows pede a senha da sua conta para a tarefa rodar na inicialização, antes do logon. Se a
   conta não tiver senha (só PIN ou Windows Hello) e o registro falhar, use o gatilho de logon:
   o agente passa a rodar só depois que você entra na conta.

   ```
   powershell -ExecutionPolicy Bypass -File .\instalar_tarefa.ps1 -Gatilho Logon
   ```

   A tarefa roda sem privilégio de administrador: desligar o PC não precisa dele.

## Remover

```
Unregister-ScheduledTask -TaskName RobotAgente -Confirm:$false
cmdkey /delete:robot-agente
```

## Testes

`python scripts/verificar.py --completo`, na raiz do repositório. Os testes substituem a rede e o
`shutdown`: nenhum teste desliga máquina nenhuma.

## Limitações conhecidas

- O Credential Manager, a tarefa agendada e o desligamento real só rodam no Windows: são aceite manual.
- A tarefa na inicialização depende de a conta do Windows ter senha que o Agendador aceite guardar.
- Se o relógio do PC estiver mais de alguns minutos errado, a AWS recusa a assinatura e o log mostra HTTP 403.
- A idade do comando compara o horário da AWS com o relógio do PC. Com o relógio alguns segundos
  adiantado, um comando dado nesses primeiros segundos após o agente subir é descartado (aparece no log).
- O agente lê o código da pasta do repositório: quem pode alterar essa pasta pode alterar o que a tarefa executa.
