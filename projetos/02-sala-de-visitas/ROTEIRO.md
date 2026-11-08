# O Brasil que a Gente Viveu — "A sala de visitas"

Duração-alvo: ~55 s · 9:16 (versão 16:9 com layout de cartão) · 8 momentos · ~110 palavras
Tema escolhido após pesquisa: rituais domésticos e objetos que sumiram das casas (sala de visitas,
sofá com capa plástica, xícaras da cristaleira, lata de biscoito com linha de costura).

| # | Voz | Fala | Imagem (nova, gerada com Gemini) |
|---|---|---|---|
| 01 | Narradora | Toda casa tinha um cômodo onde ninguém entrava: a sala de visitas. | Sala de visitas anos 80, sofá florido com capa plástica transparente, paninhos de crochê, sem pessoas |
| 02 | Narradora | As xícaras boas moravam na cristaleira. Só saíam quando chegava visita. | Cristaleira com jogo de xícaras de porcelana, luz da tarde, sem pessoas |
| 03 | Lulinha | Eu sentei uma vez naquele sofá de plástico. No verão, levantei com o sofá junto. | Lulinha (referência) sentado sem jeito no sofá plastificado |
| 04 | Mona | Lá em casa, a visita nem chegava no portão e minha mãe já tirava a capa do sofá. | Mona (referência) espiando pela janela, curiosa |
| 05 | Bonozinho | E aquele paninho de crochê? Tinha um em cima de cada coisa. Até da televisão. | Bonozinho (referência) segurando um paninho de crochê ao lado da TV |
| 06 | Narradora | E a lata de biscoito... quase sempre guardava linha e agulha. | Lata redonda azul aberta com carretéis, agulhas e botões, sem marca, sem pessoas |
| 07 | Lulinha | Pois hoje eu vim de visita. Cadê o biscoito? | Lulinha (referência) sentado formal, mãos nos joelhos, esperançoso |
| 08 | Júlia | Abre, Lulinha. Se achar biscoito, me avisa: eu procuro desde oitenta e sete. | Júlia (referência) oferecendo a lata azul aberta, sorriso seco |

Regras herdadas do pacote anterior: uma voz por trecho; narradora só em planos sem rostos; movimentos
de 2–4 %; legendas sem cobrir rostos/objetos centrais; sem vinheta, CTA pulsante ou risada gravada;
final na fala de Júlia com reação ≤ 0,5 s.

## Status (08/11/2026)

- Vozes geradas no ElevenLabs (flow "O Brasil que a Gente Viveu — Ep 02 A sala de visitas (falas)"),
  mesmo elenco do episódio 01, em `narracao/01.mp3` … `08.mp3`. Fala total 40,8 s → vídeo ≈ 45 s.
- Imagens: PENDENTES. A chave Gemini usada está no plano gratuito (cota 0 para modelos de imagem).
  Com faturamento ativo, gerar com `scripts/gemini_media.py image --model models/gemini-3-pro-image`
  usando os retratos do episódio 01 como `--ref` e salvar em `imagens/`.
