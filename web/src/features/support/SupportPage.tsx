import { PageHeader } from '@/components/PageHeader';

function Card({ heading, children }: { heading: string; children: string }) {
  return (
    <section
      aria-label={heading}
      className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-5 shadow-card"
    >
      <h2 className="text-base font-bold">{heading}</h2>
      <p className="text-sm text-muted">{children}</p>
    </section>
  );
}

/** Static help, true to how this app actually works (no hotline: it is a single-machine offline app). */
export function SupportPage() {
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        title="Support"
        subtitle="Where to look and who to ask when something isn't working."
      />
      <Card heading="This app works fully offline">
        PetrolPumpERP runs entirely on this machine - no internet connection, cloud service, or
        remote server is involved in day-to-day use. A connectivity problem on this device is never
        the cause of a screen not loading; a database or printer problem is a more likely place to
        look.
      </Card>
      <div className="grid gap-6 md:grid-cols-2">
        <Card heading="Account or access problem">
          Locked out, need a password reset, or need a role/permission changed? An Admin or Owner
          can unlock, reset, or reassign your account from Users. If you don't know who that is at
          your pump, ask your shift manager.
        </Card>
        <Card heading="Lost or corrupted data">
          Every backup taken by this app - manual or automatic - is listed on the Backups screen,
          along with an integrity check and restore. The off-device backup folder (a USB drive or
          network location) is set on the Settings screen and is the only protection against a
          failed disk, theft, or ransomware on this machine.
        </Card>
      </div>
    </div>
  );
}
