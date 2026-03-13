import { Router } from "express";
import { handleLead } from "../services/leadHandler";
import { handleTwilioSms, handleTwilioVoice, handleStatus } from "../services/twilioWebhook";

const router = Router();

// Endpoint to receive incoming leads (Zapier/CRM)
router.post("/lead", async (req, res) => {
  try {
    await handleLead(req.body);
    res.status(200).send({ ok: true });
  } catch (err) {
    res.status(500).send({ error: String(err) });
  }
});

// Twilio SMS webhook
router.post("/twilio/sms", async (req, res) => {
  try {
    await handleTwilioSms(req);
    res.status(200).send("<Response></Response>");
  } catch (err) {
    res.status(500).send("<Response></Response>");
  }
});

// Twilio Voice webhook
router.post("/twilio/voice", async (req, res) => {
  try {
    await handleTwilioVoice(req, res);
  } catch (err) {
    res.status(500).send("<Response></Response>");
  }
});

// Twilio status callbacks
router.post("/twilio/status", async (req, res) => {
  try {
    await handleStatus(req.body);
    res.status(200).send({ ok: true });
  } catch (err) {
    res.status(500).send({ error: String(err) });
  }
});

export default router;