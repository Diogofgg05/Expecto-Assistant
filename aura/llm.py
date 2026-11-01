            payload = {
                    'model': self.settings.ollama_model,
                    'messages': messages,
                    'stream': on_token is not None,
                    'keep_alive': self.settings.ollama_keep_alive,
                    'options': {'num_predict': profile.max_predict, 'temperature': 0.35 if profile.name == 'fast' else 0.45},
                }
                if on_token is None:
                    resp = await client.post(self.settings.ollama_url + '/api/chat', json=payload)
                    if resp.status_code == 404:
                        return (f'O modelo {self.settings.ollama_model} não está instalado. '
                                f'Executa: ollama pull {self.settings.ollama_model}.')
                    resp.raise_for_status()
                    answer = resp.json().get('message', {}).get('content', '').strip()
                    completed = bool(answer)
                    return answer or 'O modelo respondeu sem texto. Tenta novamente.'
                # Ollama emits newline-delimited JSON. Relay each generated token
                # immediately; keep exact concatenated text for memory capture.
                async with client.stream('POST', self.settings.ollama_url + '/api/chat',
                                         json=payload) as resp:
                    if resp.status_code == 404:
                        return (f'O modelo {self.settings.ollama_model} não está instalado. '
                                f'Executa: ollama pull {self.settings.ollama_model}.')
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        if event.get('error'):
                            raise ValueError('Ollama streaming failed')
                        piece = event.get('message', {}).get('content', '')
                        if isinstance(piece, str) and piece:
                            chunks.append(piece)
                            if first_token_at is None:
                                first_token_at = time.perf_counter()
                            await on_token(piece)
                completed = bool(chunks)
                return ''.join(chunks).strip() or 'O modelo respondeu sem texto. Tenta novamente.'
        except httpx.ConnectError:
            if chunks and on_token is not None:
                raise  # Partial response: never persist as a completed exchange.
            return ('Não consigo contactar o Ollama. Abre o Ollama, confirma que '
                    'está a executar e tenta novamente. Os comandos da interface '
                    'e a memória local continuam disponíveis.')
        except httpx.TimeoutException:
            if chunks and on_token is not None:
                raise
            return ('Ollama excedeu o tempo de resposta. Experimenta um modelo '
                    'mais pequeno ou verifica a memória RAM e a utilização da CPU.')
        except (httpx.HTTPError, ValueError):
            if chunks and on_token is not None:
                raise  # Do not mark partial output as a completed response.
            return 'Ocorreu um erro na comunicação com o modelo local. Verifica os diagnósticos.'
        finally:
            self.metrics.record(
                profile=profile.name, prep_ms=prep_ms,
                total_ms=(time.perf_counter() - started) * 1000,
                ttft_ms=((first_token_at - started) * 1000 if first_token_at is not None else None),
                context_chars=context_chars, ok=completed,
                provider=usage,
            )
            payload = {
                'model': self.settings.ollama_model,
                'messages': messages,
                'stream': on_token is not None,
                'keep_alive': self.settings.ollama_keep_alive,
                'options': {'num_predict': profile.max_predict, 'temperature': 0.35 if profile.name == 'fast' else 0.45},
            }
            if on_token is None:
                resp = await client.post(self.settings.ollama_url + '/api/chat', json=payload)
                if resp.status_code == 404:
                    return (f'O modelo {self.settings.ollama_model} não está instalado. '
                            f'Executa: ollama pull {self.settings.ollama_model}.')
                resp.raise_for_status()
                body = resp.json()
                usage = body
                answer = body.get('message', {}).get('content', '').strip()
                completed = bool(answer)
                return answer or 'O modelo respondeu sem texto. Tenta novamente.'
            # Ollama emits newline-delimited JSON. Relay each generated token
            # immediately; keep exact concatenated text for memory capture.
            async with client.stream('POST', self.settings.ollama_url + '/api/chat',
                                     json=payload) as resp:
                if resp.status_code == 404:
                    return (f'O modelo {self.settings.ollama_model} não está instalado. '
                            f'Executa: ollama pull {self.settings.ollama_model}.')
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get('done'):
                        usage = event
                    if event.get('error'):
                        raise ValueError('Ollama streaming failed')
                    piece = event.get('message', {}).get('content', '')
                    if isinstance(piece, str) and piece:
                        chunks.append(piece)
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        await on_token(piece)
            completed = bool(chunks)
            return ''.join(chunks).strip() or 'O modelo respondeu sem texto. Tenta novamente.'
        except httpx.ConnectError:
            if chunks and on_token is not None:
                raise  # Partial response: never persist as a completed exchange.
            return ('Não consigo contactar o Ollama. Abre o Ollama, confirma que '
                    'está a executar e tenta novamente. Os comandos da interface '
                    'e a memória local continuam disponíveis.')
        except httpx.TimeoutException:
            if chunks and on_token is not None:
                raise
            return ('Ollama excedeu o tempo de resposta. Experimenta um modelo '
                    'mais pequeno ou verifica a memória RAM e a utilização da CPU.')
        except (httpx.HTTPError, ValueError):
            if chunks and on_token is not None:
                raise  # Do not mark partial output as a completed response.
            return 'Ocorreu um erro na comunicação com o modelo local. Verifica os diagnósticos.'
        finally:
            self.metrics.record(
                profile=profile.name, prep_ms=prep_ms,
                total_ms=(time.perf_counter() - started) * 1000,
                ttft_ms=((first_token_at - started) * 1000 if first_token_at is not None else None),
                context_chars=context_chars, ok=completed,
            )
