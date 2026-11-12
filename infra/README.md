# Infra (AWS SAM)

Região `us-east-1`, a que a documentação da Alexa listava para pt-BR em 10/11/2026 (conferir na
documentação vigente antes do deploy).
O template cria a Lambda `robot-lambda`, a tabela `robot-tokens`, a fila `robot-comandos` e o
usuário IAM `robot-agente` (só lê e apaga mensagens dessa fila).

## Antes do deploy

1. Fase 1 e 2 do plano concluídas.
2. Criar a skill Smart Home em modo de desenvolvimento no Alexa Developer Console, com idioma
   Português (Brasil), e anotar o ID da skill.
3. Em Permissions, ligar "Send Alexa Events" e anotar o Alexa Client Id e o Alexa Client Secret.

## Deploy manual

```
sam build --template infra/template.yaml
sam deploy --guided --template infra/template.yaml --region us-east-1 --profile robot --capabilities CAPABILITY_NAMED_IAM
```

O `--guided` pergunta os quatro parâmetros (`SkillId`, `MacDoPc`, `LwaClientId`, `LwaClientSecret`).
O MAC exige o formato `XX-XX-XX-XX-XX-XX`, com hífens.
Eles ficam só na AWS. O `samconfig.toml` está no `.gitignore` e não pode ser commitado.

Depois do deploy, copie o ARN da função para o campo "Default endpoint" da skill.

O `--capabilities CAPABILITY_NAMED_IAM` é necessário a partir da fase 4, porque o template cria um
usuário IAM com nome fixo. Sem ele o deploy falha.

## Fase 4: fila, agente e desligar

1. Refaça o deploy (comandos acima). A saída `FilaUrl` mostra a URL da fila; ela contém o número
   da conta e não vai para o Git.
2. Crie a chave de acesso do agente. O segredo aparece uma única vez, só no terminal:

   ```
   aws iam create-access-key --user-name robot-agente --profile robot
   ```

3. Instale o agente no PC seguindo `agente/README.md`. O segredo é digitado na configuração do
   agente e vai para o Credential Manager; não o salve em arquivo. Feche o terminal depois.

### Aceite da fase 4 (manual, na plataforma)

Salve o que estiver aberto antes: os testes desligam o PC de verdade.

1. Com o agente rodando, abra a fila `robot-comandos` no console do SQS, "Enviar e receber
   mensagens", e envie uma mensagem fora da lista, por exemplo `{"versao": 1, "acao": "reboot"}`.
   Nada deve acontecer, e o log do agente deve registrar o descarte.
2. Envie `{"versao": 1, "acao": "shutdown"}`. O Windows deve avisar e desligar em 30 s
   (`shutdown /a` cancela).
3. Ligue o PC e, sem entrar na conta (tela de login), diga "Alexa, desligar o PC". Deve desligar.
4. Com o PC desligado, diga "Alexa, desligar o PC" e ligue o PC em seguida. Ele deve ficar ligado.
5. "Alexa, ligar o PC" deve continuar funcionando.

Se o agente foi registrado com `-Gatilho Logon`, faça o passo 3 depois de entrar na conta e anote isso no resultado.

Para trocar a chave do agente, sempre com o nome do usuário, para não mexer em outra chave:

```
aws iam list-access-keys --user-name robot-agente --profile robot
aws iam delete-access-key --user-name robot-agente --access-key-id ID_DA_CHAVE_ANTIGA --profile robot
aws iam create-access-key --user-name robot-agente --profile robot
```

Depois rode de novo `python -m robot_agente.configurar`.

## Limitações conhecidas

- Os testes automáticos não exercitam a Alexa, o Wake-on-LAN nem a Lambda implantada.
- A invocação interna (`robot_interno`) não é assinada: quem tem `lambda:InvokeFunction` na conta consegue
  disparar um "ligar" legítimo. Aceito por ser skill pessoal; reavaliar se a skill for publicada.
- Os parâmetros viram variáveis de ambiente da Lambda e ficam visíveis a quem tem acesso ao console da conta.
- O estado de energia não é consultado: a Alexa não sabe se o PC está ligado, e responde "ok" ao
  desligar mesmo que o agente esteja parado.
- A chave do `robot-agente` é de longa duração. Ela só lê e apaga mensagens da fila: quem a obtiver
  consegue no máximo impedir um desligamento, nunca provocar um.
- Quem tem `sqs:SendMessage` na conta consegue desligar o PC. Aceito por ser conta pessoal.
