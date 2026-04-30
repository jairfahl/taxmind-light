"""
src/email_service.py — Serviço de envio de e-mails transacionais via Resend HTTP API.

Usa urllib.request (stdlib Python) — zero dependência nova.
Configurado via variáveis de ambiente:
  RESEND_API_KEY  — API key do Resend (obrigatório)
  RESEND_FROM     — remetente (default: Tribus-AI <noreply@tribus-ai.com.br>)
  APP_URL         — base URL da aplicação para links de verificação

Se RESEND_API_KEY ausente: loga warning e retorna sem erro (dev-safe).
Domínio remetente deve estar verificado em resend.com/domains.
"""

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
_RESEND_FROM    = os.getenv("RESEND_FROM", "Orbis.tax <noreply@orbis.tax>")
_APP_URL        = os.getenv("APP_URL", "http://localhost:3000")

_RESEND_ENDPOINT = "https://api.resend.com/emails"


def _api_configurada() -> bool:
    return bool(_RESEND_API_KEY)


def _enviar(destinatario: str, assunto: str, html: str) -> dict:
    """Envia e-mail HTML via Resend HTTP API."""
    payload = json.dumps({
        "from":    _RESEND_FROM,
        "to":      [destinatario],
        "subject": assunto,
        "html":    html,
    }).encode("utf-8")

    req = urllib.request.Request(
        _RESEND_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {_RESEND_API_KEY}",
            "Content-Type":  "application/json",
            "User-Agent":    "tribus-ai/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API {exc.code}: {body}") from exc


def enviar_email_confirmacao(email: str, nome: str, token: str) -> None:
    """
    Envia e-mail de confirmação de cadastro com link de verificação.

    Args:
        email : E-mail do destinatário
        nome  : Nome do usuário para personalização
        token : UUID de verificação
    """
    if not _api_configurada():
        logger.warning(
            "RESEND_API_KEY não configurada — e-mail de confirmação não enviado para %s. "
            "Configure RESEND_API_KEY para ativar o envio.",
            email,
        )
        return

    link = f"{_APP_URL}/verify-email?token={token}"
    primeiro_nome = nome.split()[0] if nome else "usuário"

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">

        <!-- Cabeçalho -->
        <tr>
          <td style="background:#1a2f4e;padding:32px 40px;text-align:center">
            <span style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px">
              Orbis<span style="color:#3B9EE8">.tax</span>
            </span>
            <p style="margin:4px 0 0;font-size:11px;color:rgba(255,255,255,.55);
                      letter-spacing:2px;text-transform:uppercase">
              Inteligência Tributária
            </p>
          </td>
        </tr>

        <!-- Corpo -->
        <tr>
          <td style="padding:40px 40px 32px">
            <h1 style="margin:0 0 16px;font-size:22px;color:#1a2f4e;font-weight:700">
              Confirme seu e-mail
            </h1>
            <p style="margin:0 0 12px;font-size:15px;color:#4a5568;line-height:1.6">
              Olá, <strong>{primeiro_nome}</strong>!
            </p>
            <p style="margin:0 0 28px;font-size:15px;color:#4a5568;line-height:1.6">
              Seu cadastro na Orbis.tax foi recebido. Clique no botão abaixo para confirmar
              seu e-mail e ativar seu período de teste gratuito de <strong>7 dias</strong>.
            </p>

            <!-- CTA -->
            <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px">
              <tr>
                <td style="background:#2E75B6;border-radius:6px">
                  <a href="{link}"
                     style="display:inline-block;padding:14px 36px;font-size:15px;
                            font-weight:600;color:#ffffff;text-decoration:none;
                            letter-spacing:0.2px">
                    Confirmar e-mail
                  </a>
                </td>
              </tr>
            </table>

            <p style="margin:0 0 8px;font-size:13px;color:#718096;line-height:1.5">
              Ou copie e cole este link no navegador:
            </p>
            <p style="margin:0 0 28px;font-size:12px;color:#3B9EE8;word-break:break-all">
              {link}
            </p>

            <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 24px">
            <p style="margin:0;font-size:12px;color:#a0aec0;line-height:1.5">
              Se você não solicitou este cadastro, ignore este e-mail.
              Nenhuma ação é necessária da sua parte.
            </p>
          </td>
        </tr>

        <!-- Rodapé -->
        <tr>
          <td style="background:#f7fafc;padding:20px 40px;text-align:center;
                     border-top:1px solid #e2e8f0">
            <p style="margin:0;font-size:11px;color:#a0aec0">
              © 2026 Orbis.tax · Inteligência Tributária para a Reforma Tributária
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    try:
        result = _enviar(email, "Confirme seu e-mail — Orbis.tax", html)
        logger.info("E-mail de confirmação enviado para %s (id=%s)", email, result.get("id"))
    except Exception as e:
        logger.error("Falha ao enviar e-mail de confirmação para %s: %s", email, e)


def enviar_email_recuperacao_senha(email: str, nome: str, token: str) -> None:
    """
    Envia e-mail com link para redefinição de senha. Token válido por 1 hora.
    """
    if not _api_configurada():
        logger.warning("RESEND_API_KEY não configurada — e-mail de recuperação não enviado para %s.", email)
        return

    link = f"{_APP_URL}/redefinir-senha?token={token}"
    primeiro_nome = nome.split()[0] if nome else "usuário"

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">
        <tr>
          <td style="background:#1a2f4e;padding:32px 40px;text-align:center">
            <span style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px">
              Orbis<span style="color:#3B9EE8">.tax</span>
            </span>
            <p style="margin:4px 0 0;font-size:11px;color:rgba(255,255,255,.55);
                      letter-spacing:2px;text-transform:uppercase">Inteligência Tributária</p>
          </td>
        </tr>
        <tr>
          <td style="padding:40px 40px 32px">
            <h1 style="margin:0 0 16px;font-size:22px;color:#1a2f4e;font-weight:700">Redefinir senha</h1>
            <p style="margin:0 0 12px;font-size:15px;color:#4a5568;line-height:1.6">
              Olá, <strong>{primeiro_nome}</strong>!
            </p>
            <p style="margin:0 0 28px;font-size:15px;color:#4a5568;line-height:1.6">
              Recebemos uma solicitação para redefinir a senha da sua conta Orbis.tax.
              Clique no botão abaixo. Este link é válido por <strong>1 hora</strong>.
            </p>
            <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px">
              <tr>
                <td style="background:#2E75B6;border-radius:6px">
                  <a href="{link}"
                     style="display:inline-block;padding:14px 36px;font-size:15px;
                            font-weight:600;color:#ffffff;text-decoration:none">
                    Redefinir senha
                  </a>
                </td>
              </tr>
            </table>
            <p style="margin:0 0 8px;font-size:13px;color:#718096">Ou copie o link:</p>
            <p style="margin:0 0 28px;font-size:12px;color:#3B9EE8;word-break:break-all">{link}</p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 24px">
            <p style="margin:0;font-size:12px;color:#a0aec0;line-height:1.5">
              Se você não solicitou a redefinição, ignore este e-mail. Sua senha permanece inalterada.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f7fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0">
            <p style="margin:0;font-size:11px;color:#a0aec0">
              © 2026 Orbis.tax · Inteligência Tributária para a Reforma Tributária
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    try:
        result = _enviar(email, "Redefinição de senha — Orbis.tax", html)
        logger.info("E-mail de recuperação enviado para %s (id=%s)", email, result.get("id"))
    except Exception as e:
        logger.error("Falha ao enviar e-mail de recuperação para %s: %s", email, e)


def enviar_email_trial_expirando(email: str, nome: str, dias_restantes: int) -> None:
    """
    Envia aviso de encerramento próximo do trial (D-2 ou D-1).

    Args:
        email          : E-mail do destinatário
        nome           : Nome do usuário
        dias_restantes : 2 ou 1
    """
    if not _api_configurada():
        logger.warning("RESEND_API_KEY não configurada — e-mail de trial não enviado para %s.", email)
        return

    link_assinar = f"{_APP_URL}/assinar"
    primeiro_nome = nome.split()[0] if nome else "usuário"

    if dias_restantes == 1:
        urgencia = "Seu trial encerra <strong>amanhã</strong>."
        assunto  = "Último dia de trial — Orbis.tax"
        cor_faixa = "#dc2626"
    else:
        urgencia = f"Seu trial encerra em <strong>{dias_restantes} dias</strong>."
        assunto  = f"Seu trial Orbis.tax encerra em {dias_restantes} dias"
        cor_faixa = "#1d4ed8"

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">
        <tr>
          <td style="background:{cor_faixa};padding:10px 40px;text-align:center">
            <span style="font-size:13px;font-weight:600;color:#ffffff">{urgencia}</span>
          </td>
        </tr>
        <tr>
          <td style="background:#1a2f4e;padding:28px 40px;text-align:center">
            <span style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px">
              Orbis<span style="color:#3B9EE8">.tax</span>
            </span>
            <p style="margin:4px 0 0;font-size:11px;color:rgba(255,255,255,.55);
                      letter-spacing:2px;text-transform:uppercase">Inteligência Tributária</p>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 40px 28px">
            <p style="margin:0 0 12px;font-size:15px;color:#4a5568;line-height:1.6">
              Olá, <strong>{primeiro_nome}</strong>!
            </p>
            <p style="margin:0 0 20px;font-size:15px;color:#4a5568;line-height:1.6">
              Você ainda tem acesso completo ao <strong>Orbis.tax</strong> — protocolo auditável P1→P6,
              análise RAG ilimitada com citação de fonte e simuladores tributários para IBS, CBS e Split Payment.
            </p>
            <p style="margin:0 0 28px;font-size:15px;color:#1a2f4e;font-weight:600">
              Para continuar usando sem interrupção, assine agora por R$&nbsp;297/mês nos primeiros 2 meses.
            </p>
            <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px">
              <tr>
                <td style="background:linear-gradient(135deg,#2E75B6 0%,#1F3864 100%);border-radius:6px">
                  <a href="{link_assinar}"
                     style="display:inline-block;padding:14px 40px;font-size:15px;
                            font-weight:600;color:#ffffff;text-decoration:none">
                    Assinar agora — R$&nbsp;297/mês
                  </a>
                </td>
              </tr>
            </table>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 20px">
            <p style="margin:0;font-size:12px;color:#a0aec0;line-height:1.5">
              Dúvidas? Fale com a gente pelo
              <a href="https://wa.me/5511972521970" style="color:#3B9EE8;text-decoration:none">WhatsApp</a>.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f7fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0">
            <p style="margin:0;font-size:11px;color:#a0aec0">
              © 2026 Orbis.tax · Inteligência Tributária para a Reforma Tributária
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    try:
        result = _enviar(email, assunto, html)
        logger.info("E-mail trial D-%d enviado para %s (id=%s)", dias_restantes, email, result.get("id"))
    except Exception as e:
        logger.error("Falha ao enviar e-mail trial D-%d para %s: %s", dias_restantes, email, e)


def enviar_email_falha_pagamento(email: str, nome: str) -> None:
    """
    Notifica o usuário sobre falha no pagamento da assinatura.
    """
    if not _api_configurada():
        logger.warning("RESEND_API_KEY não configurada — e-mail de falha de pagamento não enviado para %s.", email)
        return

    link_assinar = f"{_APP_URL}/assinar"
    primeiro_nome = nome.split()[0] if nome else "usuário"

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">
        <tr>
          <td style="background:#dc2626;padding:10px 40px;text-align:center">
            <span style="font-size:13px;font-weight:600;color:#ffffff">
              Problema identificado no seu pagamento
            </span>
          </td>
        </tr>
        <tr>
          <td style="background:#1a2f4e;padding:28px 40px;text-align:center">
            <span style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px">
              Orbis<span style="color:#3B9EE8">.tax</span>
            </span>
            <p style="margin:4px 0 0;font-size:11px;color:rgba(255,255,255,.55);
                      letter-spacing:2px;text-transform:uppercase">Inteligência Tributária</p>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 40px 28px">
            <p style="margin:0 0 12px;font-size:15px;color:#4a5568;line-height:1.6">
              Olá, <strong>{primeiro_nome}</strong>!
            </p>
            <p style="margin:0 0 20px;font-size:15px;color:#4a5568;line-height:1.6">
              Não foi possível processar o pagamento da sua assinatura Orbis.tax.
              Para evitar a suspensão do acesso, atualize sua forma de pagamento.
            </p>
            <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px">
              <tr>
                <td style="background:linear-gradient(135deg,#2E75B6 0%,#1F3864 100%);border-radius:6px">
                  <a href="{link_assinar}"
                     style="display:inline-block;padding:14px 40px;font-size:15px;
                            font-weight:600;color:#ffffff;text-decoration:none">
                    Regularizar pagamento
                  </a>
                </td>
              </tr>
            </table>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 20px">
            <p style="margin:0;font-size:12px;color:#a0aec0;line-height:1.5">
              Precisa de ajuda? Fale com a gente pelo
              <a href="https://wa.me/5511972521970" style="color:#3B9EE8;text-decoration:none">WhatsApp</a>.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f7fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0">
            <p style="margin:0;font-size:11px;color:#a0aec0">
              © 2026 Orbis.tax · Inteligência Tributária para a Reforma Tributária
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    try:
        result = _enviar(email, "Problema com seu pagamento — Orbis.tax", html)
        logger.info("E-mail de falha de pagamento enviado para %s (id=%s)", email, result.get("id"))
    except Exception as e:
        logger.error("Falha ao enviar e-mail de falha de pagamento para %s: %s", email, e)


def enviar_email_inatividade(email: str, nome: str) -> None:
    """
    Reengajamento para assinantes ativos sem análise nos últimos 14 dias.
    """
    if not _api_configurada():
        logger.warning("RESEND_API_KEY não configurada — e-mail de inatividade não enviado para %s.", email)
        return

    link_analisar = f"{_APP_URL}/analisar"
    primeiro_nome = nome.split()[0] if nome else "usuário"

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">
        <tr>
          <td style="background:#1a2f4e;padding:32px 40px;text-align:center">
            <span style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px">
              Orbis<span style="color:#3B9EE8">.tax</span>
            </span>
            <p style="margin:4px 0 0;font-size:11px;color:rgba(255,255,255,.55);
                      letter-spacing:2px;text-transform:uppercase">Inteligência Tributária</p>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 40px 28px">
            <h1 style="margin:0 0 16px;font-size:22px;color:#1a2f4e;font-weight:700">
              Sentimos sua falta, {primeiro_nome}!
            </h1>
            <p style="margin:0 0 20px;font-size:15px;color:#4a5568;line-height:1.6">
              Faz um tempo que você não abre o Orbis.tax. A Reforma Tributária continua avançando —
              novos atos do IBS e CBS são publicados regularmente e a base de normas está atualizada.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f0f7ff;border-radius:8px;margin:0 0 28px">
              <tr>
                <td style="padding:20px 24px">
                  <p style="margin:0 0 10px;font-size:13px;font-weight:700;color:#1a2f4e;
                             text-transform:uppercase;letter-spacing:0.5px">
                    O que está esperando por você
                  </p>
                  <ul style="margin:0;padding:0 0 0 18px;font-size:14px;color:#4a5568;line-height:1.8">
                    <li>Análise RAG com citação de fonte (1.596 normas indexadas)</li>
                    <li>Protocolo auditável P1→P6 completo</li>
                    <li>Simuladores de IBS, CBS e Split Payment</li>
                    <li>Outputs acionáveis em 5 formatos</li>
                  </ul>
                </td>
              </tr>
            </table>
            <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px">
              <tr>
                <td style="background:linear-gradient(135deg,#2E75B6 0%,#1F3864 100%);border-radius:6px">
                  <a href="{link_analisar}"
                     style="display:inline-block;padding:14px 40px;font-size:15px;
                            font-weight:600;color:#ffffff;text-decoration:none">
                    Fazer uma análise agora
                  </a>
                </td>
              </tr>
            </table>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 20px">
            <p style="margin:0;font-size:12px;color:#a0aec0;line-height:1.5">
              Tem alguma dúvida ou sugestão? Fale com a gente pelo
              <a href="https://wa.me/5511972521970" style="color:#3B9EE8;text-decoration:none">WhatsApp</a>.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f7fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0">
            <p style="margin:0;font-size:11px;color:#a0aec0">
              © 2026 Orbis.tax · Inteligência Tributária para a Reforma Tributária
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    try:
        result = _enviar(email, f"Sentimos sua falta, {primeiro_nome}! — Orbis.tax", html)
        logger.info("E-mail de inatividade enviado para %s (id=%s)", email, result.get("id"))
    except Exception as e:
        logger.error("Falha ao enviar e-mail de inatividade para %s: %s", email, e)
