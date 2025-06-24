# email_manager.py

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config


class EmailManager:
    def __init__(self):
        self.sender_email = config.SENDER_EMAIL
        self.password = config.SENDER_PASSWORD
        self.smtp_server = "smtp.gmail.com"
        self.port = 465

    def _send_email(self, recipient_email, subject, html_body):
        if not recipient_email:
            print(f"AVISO: Email não fornecido. Envio cancelado.")
            return
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"Casona Açaí - Clube Fidelidade <{self.sender_email}>"
        message["To"] = recipient_email
        message.attach(MIMEText(html_body, "html"))
        context = ssl.create_default_context()
        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.port, context=context) as server:
                server.login(self.sender_email, self.password)
                server.sendmail(self.sender_email, recipient_email, message.as_string())
        except Exception as e:
            print(f"ERRO AO ENVIAR EMAIL: {e}")

    def send_welcome_email(self, recipient_email, nome, codigo):
        subject = "Bem-vindo(a) ao nosso Clube Fidelidade - Casona Açaí!"
        html_body = f"""
        <html><body>
            <h2>Olá, {nome}!</h2>
            <p>Seu cadastro em nosso novo programa de fidelidade foi realizado com sucesso.</p>
            <p>Seu código de cliente exclusivo é: <strong>{codigo}</strong></p>
            <p>Apresente este código em todas as suas compras para acumular pontos!</p>
            <hr>
            <h4>Como funciona:</h4>
            <ul>
                <li><b>Acumule Pontos:</b> A cada R$ 1,00 gasto, você ganha 100 pontos.</li>
                <li><b>Resgate seu Prêmio:</b> Após sua 5ª compra, um código de prêmio será gerado e você já poderá resgatar seus pontos acumulados como desconto!</li>
                <li><b>Validade:</b> Fique atento! Os pontos de cada compra expiram após 6 meses.</li>
            </ul>
            <hr>
            <p>Atenciosamente,<br>Equipe Casona Açaí</p>
        </body></html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_purchase_update_email(self, recipient_email, nome, resultado_compra: dict):
        subject = "Atualização do seu Clube Fidelidade Casona Açaí!"

        pontos_nesta_compra = resultado_compra.get("pontos_nesta_compra", 0)
        compras_no_ciclo = resultado_compra.get("compras_no_ciclo", 0)
        pontos_acumulados = resultado_compra.get("pontos_acumulados", 0)
        premio_gerado_agora = resultado_compra.get("premio_gerado_nesta_compra", False)
        codigo_premio_ativo = resultado_compra.get("codigo_premio_ativo")

        mensagem_status = ""
        if premio_gerado_agora and codigo_premio_ativo:
            mensagem_status = f"""
            <p style="font-size: 18px; color: #8B008B; font-weight: bold;">
                Parabéns! Você atingiu a 5ª compra e seu prêmio foi gerado!
            </p>
            <div style="border: 2px dashed #8B008B; padding: 10px; margin: 15px 0; text-align: center;">
                <p style="margin: 0; font-size: 16px;">Seu código para resgate é:</p>
                <p style="margin: 5px 0 0 0; font-size: 24px; font-weight: bold; letter-spacing: 2px;">
                    {codigo_premio_ativo}
                </p>
            </div>
            <p>
                Apresente este código no caixa para usar seus pontos como desconto.
                Continue comprando para acumular ainda mais pontos no seu prêmio!
            </p>
            """
        elif compras_no_ciclo >= 5:
            mensagem_status = """
            <p>
                Você adicionou mais pontos ao seu prêmio ativo! 
                Lembre-se que você <strong>já pode resgatá-lo quando quiser.</strong>
            </p>
            """
        else:
            faltam = 5 - compras_no_ciclo
            compra_texto = "compra" if faltam == 1 else "compras"
            mensagem_status = f"""
            <p>
                Falta apenas <strong>{faltam} {compra_texto}</strong> para você gerar seu código de prêmio e poder resgatar seus pontos!
            </p>
            """

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                <h2 style="color: #8B008B;">Olá, {nome}!</h2>
                <p>Obrigado por sua compra! Seu extrato de pontos foi atualizado.</p>
                <div style="background-color: #f2f2f2; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <p style="font-size: 16px; margin: 0 0 5px 0;">Pontos desta compra:</p>
                    <p style="font-size: 24px; font-weight: bold; color: #4CAF50; margin: 0 0 15px 0;">
                        + {pontos_nesta_compra}
                    </p>
                    <hr style="border: none; border-top: 1px solid #ddd;">
                    <p style="font-size: 16px; margin: 15px 0 5px 0;">Seu novo saldo total:</p>
                    <p style="font-size: 28px; font-weight: bold; color: #8B008B; margin: 0;">
                        {pontos_acumulados} pontos
                    </p>
                </div>
                {mensagem_status}
                <p>Continue conosco para aproveitar ainda mais benefícios!</p>
                <p>Atenciosamente,<br>Equipe Casona Açaí</p>
            </div>
        </body>
        </html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_redemption_success_email(self, recipient_email, nome, pontos_resgatados):
        subject = "Seu prêmio foi resgatado com sucesso!"
        html_body = f"""
        <html><body>
            <h2>Olá, {nome}!</h2>
            <p>Confirmamos que seu prêmio de <strong>{pontos_resgatados} pontos</strong> foi resgatado com sucesso em nosso estabelecimento.</p>
            <p>Seu ciclo de compras foi reiniciado e você já pode começar a juntar pontos para o próximo prêmio. Esperamos te ver em breve!</p>
            <p>Obrigado por fazer parte do nosso clube de fidelidade!</p>
            <p>Atenciosamente,<br>Equipe Casona Açaí</p>
        </body></html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_birthday_email(self, recipient_email, nome):
        subject = f"Feliz Aniversário, {nome}! 🎂"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                <h2 style="color: #8B008B;">Feliz Aniversário, {nome}!</h2>
                <p>A equipe do <strong>Casona Açaí</strong> deseja a você um dia incrível!</p>
                <p>Para comemorar, apresente este e-mail no caixa e ganhe <strong>10% DE DESCONTO</strong> em sua compra!</p>
                <p>Com carinho,<br>Equipe Casona Açaí</p>
            </div>
        </body>
        </html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_inactivity_reminder_email(self, recipient_email, nome):
        subject = f"Estamos com saudades, {nome}! 💜"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                <h2 style="color: #8B008B;">Olá, {nome}! Sentimos sua falta!</h2>
                <p>Faz um tempinho que você não passa no <strong>Casona Açaí</strong>.</p>
                <p>Seu clube de fidelidade está esperando por você para continuar acumulando pontos. Volte e continue sua jornada para o próximo prêmio!</p>
                <p>Com carinho,<br>Equipe Casona Açaí</p>
            </div>
        </body>
        </html>
        """
        self._send_email(recipient_email, subject, html_body)