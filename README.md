# AudioSocket Simple

Um sistema de comunicação de portaria inteligente baseado em AudioSocket com suporte a IA para conversação.

## Configuração de Performance

O sistema utiliza os seguintes parâmetros configuráveis para otimização de performance, disponíveis em `config.json`:

### Parâmetros de Áudio
- `transmission_delay_ms`: Delay entre transmissão de chunks de áudio (default: 20ms)
- `post_audio_delay_seconds`: Delay após envio completo do áudio (default: 0.5s)
- `discard_buffer_frames`: Número de frames para descartar após IA falar (default: 25)

### Parâmetros de Sistema
- `silence_threshold_seconds`: Tempo de silêncio para considerar que a fala terminou (default: 2.0s)

## Executando

```bash
python main.py
```

Para testes, você pode usar:

```bash
python microfone_client.py
```