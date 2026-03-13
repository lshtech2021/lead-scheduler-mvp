import Twilio from "twilio";
import { logger } from "../logger";

const client = Twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

export async function sendSms(to: string, body: string, idempotencyKey?: string) {
  // Idempotency: calling code must check DB for duplicates before invoking
  logger.info("Sending SMS", { to, body });
  return client.messages.create({
    to,
    from: process.env.TWILIO_PHONE_NUMBER,
    body,
    statusCallback: `${process.env.PUBLIC_URL}/webhook/twilio/status`
  });
}

export async function createVoiceResponse(twiml: string) {
  // Helper: TwiML response as string; controller will return to Twilio
  return `<Response>${twiml}</Response>`;
}