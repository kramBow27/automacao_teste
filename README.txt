Portal Transparência RPA

Automação em Python/Selenium para extração de dados de beneficiários de programas sociais no Portal da Transparência.

🚀 Execução rápida

python automacao_copia.py --query "TERMO" --out arquivo.json --visible --debug

Parâmetros

Parâmetro

Descrição

Valor padrão

--query

Filtro de busca (Nome, CPF ou NIS)

"" (todos)

--out

Caminho/arquivo JSON de saída

beneficiarios.json

--visible

Abre o navegador visível (desativa headless)

desligado

--debug

Mostra logs detalhados no console

desligado

📑 Sumário

Execução rápida

Contexto do teste

Considerações técnicas

Atualizações

Autor

💻 Como executar

Para a execução básica:

python automacao_copia.py

Para opções avançadas, consulte a seção Execução rápida.

📝 Contexto do teste

Atualmente estou empregado em um trabalho presencial das 08h às 18h e me foi pedido que eu entregasse o teste até sexta‑feira (09/05/2025).

Como não tenho muito tempo livre, optei por fazer o teste em um único dia (08/05/2025) e não consegui implementar todas as funcionalidades que gostaria, mas fiz o meu melhor para entregar algo funcional e que atenda ao solicitado.

O total de horas dedicadas foi de aproximadamente 6 h.

Pontos observados

O RPA obtém os dados dos beneficiados por auxílio de programa social, porém três campos no JSON permanecem vazios.

O primeiro item da lista é ignorado, fazendo com que o item da página 2 apareça como o último da lista de dez resultados.

Ainda não testei se todas as capturas de tela estão corretas, nem se deveria capturar a página inteira ou apenas o screenshot da viewport.

De qualquer maneira, o código está funcional e pode ser melhorado para atender a todos os requisitos solicitados.

Dentro do contexto de trabalho, certamente eu conseguiria implementar todas as funcionalidades solicitadas, mas devido ao tempo reduzido não foi possível.

⚙️ Considerações técnicas

Estado inicial (08/05/2025)

Capturando beneficiários, porém com três campos vazios no JSON.

Ignorando o primeiro item da lista de resultados.

Realizando screenshots, porém sem validação completa.

Correções aplicadas (09/05/2025)

Tratamento específico para cada benefício, pois suas colunas diferem.

Descoberto o endpoint da API de parcelas – captura via requisições HTTP substituiu a manipulação de DOM.

Ajustado o parâmetro de paginação (tamanhoPagina=1000) para retornar todas as parcelas em uma única chamada.

Implementado fechamento automático do painel de cookies para evitar bloqueio de cliques.

Reconhecida a limitação imposta por CAPTCHA – execução requer intervenção humana caso apareça.

Constatado que, após as correções, o sistema cumpre 100 % dos objetivos em ~95 % das execuções.

🗓 Atualizações

Data

Descrição

09/05/2025

Correções gerais: mapeamento de colunas, uso de API JSON, tratamento do cookie‑bar, paginação de 1 000 parcelas.

13/05/2025

Início do processo de refatoração e reorganização do projeto em módulos (driver.py, scraper.py, etc.).

👤 Autor

Henrique Luna

"Com certeza o sistema pode ser melhorado, pois sempre pode ser melhorado, mas atualmente diria que ele cumpre 100 % dos objetivos em aproximadamente 95 % dos casos."