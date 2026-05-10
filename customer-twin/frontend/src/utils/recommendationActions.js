// Descriptors for recommended actions ("email", "llamada", ...).
// Each handler returns a uniform shape so DetailPanel can render the accept
// button the same way regardless of the underlying action.
//
// Adding a new action (e.g. WhatsApp, schedule a meeting) is just dropping
// another entry in HANDLERS — no UI changes required.

const FALLBACK_LABELS = {
  visita: "Crear tarea: visita",
  llamada: "Crear tarea: llamada",
  email: "Preparar email",
  muestra: "Solicitar muestra",
  monitorizar: "Pasar a vigilancia",
};

const DEFAULT_CLIENT_EMAIL = "cliente@empresa.com";

function clientEmail(client) {
  if (!client) return DEFAULT_CLIENT_EMAIL;
  const candidate =
    client.email_cliente ||
    client.email ||
    client.correo ||
    null;
  if (typeof candidate !== "string") return DEFAULT_CLIENT_EMAIL;
  const trimmed = candidate.trim();
  return trimmed.length > 0 ? trimmed : DEFAULT_CLIENT_EMAIL;
}

// Customer-facing copy: no internal jargon, no metrics, no IDs or category
// codes. The salesperson reviews and personalises in Gmail before sending.
function emailSubject() {
  return "Queríamos saludarle y ofrecerle nuestra ayuda";
}

function emailBody() {
  return [
    "Estimado/a cliente,",
    "",
    "Le escribimos desde el equipo comercial para saludarle y saber cómo va todo en su día a día.",
    "",
    "Hace tiempo que queríamos ponernos en contacto con usted para conocer mejor sus necesidades actuales y comentarle,",
    "si es de su interés, en qué podemos echarle una mano en los próximos meses.",
    "",
    "Si le parece bien, podemos concertar una breve llamada o una reunión cuando mejor le venga. También puede responder",
    "directamente a este correo y nos pondremos en contacto con usted enseguida.",
    "",
    "Muchas gracias por su confianza. Quedamos a su disposición para lo que necesite.",
    "",
    "Un cordial saludo,",
    "Equipo comercial",
  ].join("\n");
}

/**
 * Build a Gmail compose URL pre-filled for the given client + alert.
 * Returns null if the client has no usable email address.
 *
 * The URL opens Gmail's "compose" view in the user's logged-in account; the
 * user still has to press Send manually (no auto-send).
 */
export function buildGmailComposeUrl(client, alert) {
  const to = clientEmail(client);
  if (!to) return null;
  const su = emailSubject(alert);
  const body = emailBody(client, alert);
  const params = new URLSearchParams({
    view: "cm",
    fs: "1",
    to,
    su,
    body,
  });
  return `https://mail.google.com/mail/?${params.toString()}`;
}

const HANDLERS = {
  email: ({ client, alert }) => {
    const href = buildGmailComposeUrl(client, alert);
    if (!href) {
      return {
        kind: "external",
        label: FALLBACK_LABELS.email,
        disabled: true,
        disabledReason: "Este cliente no tiene email registrado.",
      };
    }
    return {
      kind: "external",
      label: FALLBACK_LABELS.email,
      href,
      newTab: true,
      hint: "Se abrirá Gmail con el borrador. Revísalo antes de enviar.",
    };
  },

  // Future arms: drop a handler in here following the same shape.
  // Example stubs so the registry is self-documenting:
  //
  // llamada: ({ client }) => ({
  //   kind: "external",
  //   label: FALLBACK_LABELS.llamada,
  //   href: client?.telefono ? `tel:${client.telefono}` : undefined,
  //   disabled: !client?.telefono,
  //   disabledReason: "Este cliente no tiene teléfono registrado.",
  // }),
  //
  // whatsapp: ({ client, alert }) => ({ ... }),
  // reunion:  ({ client, alert }) => ({ ... }),  // Google Calendar deep link
  // tarea:    ({ client, alert }) => ({ ... }),  // internal task creation
};

/**
 * Resolve the descriptor for a recommended action arm.
 *
 * Always returns an object with at least { kind, label }. If the action has no
 * external integration registered, returns kind: "submit" so the caller falls
 * back to the existing feedback-only flow.
 */
export function getRecommendationAction(actionKey, { signal, detail } = {}) {
  const client = {
    id_cliente: signal?.id_cliente,
    email_cliente: signal?.email_cliente ?? signal?.email ?? detail?.client?.email,
  };
  const handler = HANDLERS[actionKey];
  if (handler) {
    return handler({ client, alert: signal, detail });
  }
  return {
    kind: "submit",
    label: FALLBACK_LABELS[actionKey] ?? "Aceptar recomendación",
  };
}
