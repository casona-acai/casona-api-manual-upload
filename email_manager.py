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
            print(f"AVISO: Email não fornecido para o destinatário. Envio cancelado.")
            return
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"Casona Açaí - Sistema de Fidelidade <{self.sender_email}>"
        message["To"] = recipient_email
        message.attach(MIMEText(html_body, "html"))
        context = ssl.create_default_context()
        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.port, context=context) as server:
                server.login(self.sender_email, self.password)
                server.sendmail(self.sender_email, recipient_email, message.as_string())
                print("Email enviado com sucesso!")
        except Exception as e:
            print(f"ERRO AO ENVIAR EMAIL: {e}")

    def send_welcome_email(self, recipient_email, nome, codigo):
        subject = "Bem-vindo(a) ao nosso Programa de Fidelidade - Casona Açaí!"
        html_body = f"""
        <html><body>
            <h2>Olá, {nome}!</h2>
            <p>Seu cadastro em nosso programa de fidelidade foi realizado com sucesso.</p>
            <p>Seu código de cliente exclusivo é: <strong>{codigo}</strong></p>
            <p>Apresente este código em todas as suas compras para acumular pontos e ganhar prêmios!</p>
            <p>Atenciosamente,</p>
            <p>Equipe Casona Açaí</p>
            <p>Não se esqueça de seguir @casona.abc</p>
        </body></html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_purchase_update_email(self, recipient_email, nome, contagem_atual):
        subject = "Nova compra Casona Açaí!"
        faltam = 10 - contagem_atual
        html_body = f"""
        <html><body>
            <h2>Olá, {nome}!</h2>
            <p>Obrigado por sua compra!</p>
            <p>Você acumulou mais um ponto. Agora você tem <strong>{contagem_atual} de 10</strong> pontos.</p>
            <p>Faltam apenas <strong>{faltam}</strong> compras para você ganhar um prêmio!</p>
            <p>Continue conosco!</p>
            <p>Atenciosamente,</p>
            <p>Equipe Casona Açaí</p>
            <p>Não se esqueça de seguir @casona.abc</p>
        </body></html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_prize_won_email(self, recipient_email, nome, codigo_premio, valor_premio):
        subject = "Parabéns! Você ganhou um prêmio!"
        html_body = f"""
        <html><body>
            <h2>Parabéns, {nome}!</h2>
            <p>Você completou seu cartão fidelidade de 10 compras e ganhou um prêmio!</p>
            <p>Seu código para resgate é: <strong>{codigo_premio}</strong></p>
            <p>Você tem um crédito de <strong>R$ {valor_premio:.2f}</strong> para usar em sua próxima compra.</p>
            <p>Apresente o código de resgate no caixa. Seu cartão fidelidade foi reiniciado.</p>
            <p>Obrigado por sua preferência!</p>
            <p>Atenciosamente,</p>
            <p>Equipe Casona Açaí</p>
            <p>Não se esqueça de seguir @casona.abc</p>
        </body></html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_redemption_success_email(self, recipient_email, nome):
        subject = "Seu prêmio foi resgatado com sucesso!"
        html_body = f"""
        <html>
        <body>
            <h2>Olá, {nome}!</h2>
            <p>Confirmamos que seu prêmio foi resgatado com sucesso em nosso estabelecimento.</p>
            <p>Seu cartão fidelidade já está pronto para um novo ciclo de compras. Esperamos te ver em breve para começar a acumular novos pontos!</p>
            <p>Obrigado por fazer parte do nosso programa de fidelidade!</p>
            <p>Atenciosamente,</p>
            <p>Equipe Casona Açaí</p>
            <p>Não se esqueça de seguir @casona.abc</p>
        </body>
        </html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_birthday_email(self, recipient_email, nome):
        subject = f"Feliz Aniversário, {nome}! 🎂"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                <h2 style="color: #8B008B;">Feliz Aniversário, {nome}!</h2>
                <p>A equipe do <strong>Casona Açaí</strong> deseja a você um dia incrível, cheio de alegria e, claro, muito açaí!</p>
                <p>Para comemorar com você, aqui está um presente especial:</p>
                <div style="background-color: #f2f2f2; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <p style="font-size: 16px; margin: 0;">Apresente este e-mail no caixa e ganhe</p>
                    <p style="font-size: 24px; font-weight: bold; color: #8B008B; margin: 10px 0;">10% DE DESCONTO</p>
                    <p style="font-size: 16px; margin: 0;">em sua próxima compra!</p>
                </div>
                <p>Esperamos te ver em breve para celebrar!</p>
                <p>Com carinho,<br>Equipe Casona Açaí</p>
                <p style="font-size: 12px; color: #777;">Não se esqueça de seguir @casona.abc</p>
            </div>
        </body>
        </html>
        """
        self._send_email(recipient_email, subject, html_body)

    def send_inactivity_reminder_email(self, recipient_email, nome):
        """Envia um e-mail para clientes que não compram há algum tempo."""
        subject = f"Estamos com saudades, {nome}! 💜"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                <h2 style="color: #8B008B;">Olá, {nome}! Sentimos sua falta!</h2>
                <p>Faz um tempinho que você não passa no <strong>Casona Açaí</strong>, e nós estamos com saudades.</p>
                <p>Seu cartão fidelidade está esperando por você para continuar acumulando pontos e ganhar prêmios incríveis.</p>
                <p>Que tal matar a saudade com um açaí delicioso hoje?</p>
                <div style="background-color: #f2f2f2; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <p style="font-size: 18px; font-weight: bold; color: #8B008B; margin: 10px 0;">
                        Volte e continue sua jornada para o próximo prêmio!
                    </p>
                </div>
                <p>Esperamos te ver em breve!</p>
                <p>Com carinho,<br>Equipe Casona Açaí</p>
                <p style="font-size: 12px; color: #777;">Não se esqueça de seguir @casona.abc</p>
            </div>
        </body>
        </html>
        """
        self._send_email(recipient_email, subject, html_body)