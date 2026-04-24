def main():
    # -*- coding: utf-8 -*-
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    import os
    #from config_test import Config

    import sys
    import json
    import argparse

    parser = argparse.ArgumentParser(description="Send Gmail with subject/body/attachment from files.")
    parser.add_argument('--subject', required=True, help='subject string')
    parser.add_argument('--body-file', required=True, help='File containing email body')
    parser.add_argument('--attach-file', default=None, help='Attachment file path (optional)')
    args = parser.parse_args()

    def read_file_content(path):
        if path and os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return f.read().strip()
        return ''

    def send_email(
        sender_email,
        sender_password,
        bcc_email,
        subject,
        body,
        attachment_path=None,
    ):
        """
        Send an email with optional attachment.

        Parameters:
        - sender_email: Your email address
        - sender_password: Your email password or app-specific password
        - receiver_email: Recipient's email address
        - subject: Email subject
        - body: Email body content
        - attachment_path: Optional path to attachment file
        """
        try:
            # Create the email message
            message = MIMEMultipart()
            message["From"] = sender_email
            message["To"] = sender_email  # To sender only
            #message["CC"] = cc_email
            message["BCC"] = bcc_email
            message["Subject"] = subject

            # Add body to email
            message.attach(MIMEText(body, "plain"))

            # Add attachment if provided
            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment.read())

                # Encode attachment
                encoders.encode_base64(part)

                # Add header to attachment
                filename = os.path.basename(attachment_path)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=("utf-8", "", filename),
                )
                message.attach(part)

            # Create SMTP session
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                # Login to the server
                server.login(sender_email, sender_password)

                # Send email
                server.send_message(message)

            print("Email sent successfully!")
            return True

        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return False


    sender_email = "cheoljoo@gmail.com"
    sender_password = "dytf xplz hjea dhwj"  # Use app-specific password for Gmail
    bcc_email = "cheoljoo.lee@lge.com,youngho.lge@gmail.com,baver.bae@gmail.com,flyingfunky@gmail.com,firstcall.n@gmail.com"   # "jihee.yu@gmail.com"
    #cc_email = "cheoljoo@gmail.com"
    subject = args.subject
    body = read_file_content(args.body_file)

    # Optional: path to attachment
    attachment_path = args.attach_file

    # Send email
    send_email(
        sender_email,
        sender_password,
        bcc_email,
        subject,
        body,
        attachment_path  # Remove this line if no attachment
    )




if __name__ == "__main__":
    main()
