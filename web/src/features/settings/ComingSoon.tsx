import { Badge, Section } from "@/ui/primitives";

const FEATURES = {
  ai: {
    title: "AI manager",
    description: "Ask about your shop in plain words. For the owner only.",
    points: [
      "“How did this week compare with last week?”",
      "What to restock, and what isn't selling",
      "Spot unusual discounts, refunds and cash gaps",
      "A short morning summary of yesterday",
    ],
  },
  whatsapp: {
    title: "WhatsApp",
    description: "Send bills and reminders on WhatsApp from your shop's number.",
    points: [
      "Send the bill to the customer after payment",
      "Polite reminders for dues, with a UPI link",
      "Daily sales summary to the owner",
      "Customers opt in once; they can stop any time",
    ],
  },
} as const;

export function ComingSoon({ feature }: { feature: keyof typeof FEATURES }) {
  const f = FEATURES[feature];
  return (
    <Section title={f.title} description={f.description}>
      <div className="space-y-3">
        <Badge tone="brand">Coming soon</Badge>
        <ul className="list-disc space-y-1.5 pl-5 text-text-2">
          {f.points.map((p) => <li key={p}>{p}</li>)}
        </ul>
      </div>
    </Section>
  );
}
