import express from "express";
import bodyParser from "body-parser";
import dotenv from "dotenv";
import webhookRoutes from "./routes/webhook";
import { initDb } from "./db";
import { logger } from "./logger";

dotenv.config();
const app = express();
app.use(bodyParser.json());

app.use("/webhook", webhookRoutes);

const port = process.env.PORT || 3000;
initDb()
  .then(() => {
    app.listen(port, () => {
      logger.info(`Server listening on ${port}`);
    });
  })
  .catch((err) => {
    logger.error("Failed to initialize DB", err);
    process.exit(1);
  });