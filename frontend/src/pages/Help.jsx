import { Card } from '../components/ui'

const REPO = 'https://github.com/jasonhaymond/haven-backup'
const DOCS = `${REPO}/blob/master/docs`

function Section({ title, children }) {
  return (
    <Card className="mb-4">
      <h2 className="mb-2 font-semibold">{title}</h2>
      <div className="space-y-2 text-sm text-slate-700 dark:text-slate-300">{children}</div>
    </Card>
  )
}

function Code({ children }) {
  return (
    <pre className="overflow-x-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">
      <code>{children}</code>
    </pre>
  )
}

function DocLink({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-slate-900 underline dark:text-slate-100">
      {children}
    </a>
  )
}

export default function Help() {
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Help</h1>

      <Section title="Getting started">
        <p>
          1. Add an <strong>SSH credential</strong> for reaching your Borg backup host. 2. Add a{' '}
          <strong>repository</strong> (its <code>ssh://</code> URL, that credential, its passphrase, and a retention
          policy) and click <strong>Refresh now</strong>. 3. Optionally add a <strong>client host</strong> to enable
          "backup now" from the browser.
        </p>
        <p>
          See <DocLink href={`${DOCS}/DEPLOYMENT.md`}>DEPLOYMENT.md</DocLink> and{' '}
          <DocLink href={`${DOCS}/BORGMATIC_INTEGRATION.md`}>BORGMATIC_INTEGRATION.md</DocLink> for the full walkthrough,
          including how retention should be split between the portal and each client's own borgmatic config.
        </p>
      </Section>

      <Section title="Retention and pruning">
        <p>
          Each repo's <strong>Keep daily/weekly/monthly/yearly</strong> settings are enforced by this portal, not by
          the clients that create archives into it -- that's deliberate, so retention isn't split across multiple
          places disagreeing with each other. Use <strong>Preview prune (dry run)</strong> on a repo's detail page
          before <strong>Apply retention now</strong> if you want to see what would be deleted first. It also runs on
          its own schedule (<code>HAVEN_PRUNE_INTERVAL_HOURS</code>, default daily).
        </p>
      </Section>

      <Section title="Restoring from a repo">
        <p>
          This portal monitors and prunes Borg repos, but restoring files is a <code>borg extract</code> or{' '}
          <code>borg mount</code> operation against the repo directly -- there's no restore feature in this UI.
          Point either command at the repo URL from that repo's detail page, using the same passphrase stored here.
          See{' '}
          <DocLink href="https://borgbackup.readthedocs.io/en/stable/usage/extract.html">Borg's own docs</DocLink> for
          the exact syntax.
        </p>
      </Section>

      <Section title="Updating the portal">
        <p>
          The sidebar shows a badge when a newer tagged release exists (checked against GitHub, cached for an hour) --
          that's visibility only. Nothing in this UI can trigger the actual update: the backend container has no git
          checkout or Docker access to rebuild itself, and giving it that access just for a button would grant it
          effective root on the host. Run this on the server instead:
        </p>
        <Code>./scripts/update.sh          # deploy latest{'\n'}./scripts/update.sh &lt;tag&gt;   # deploy/roll back to that exact tag, e.g. v0.3.0</Code>
        <p>
          It refuses to run over uncommitted changes, snapshots the portal's own data first (labeled by the version
          actually running, not the git tree), and checks <code>/api/health</code> before declaring success. Full
          detail in <DocLink href={`${DOCS}/DEPLOYMENT.md`}>DEPLOYMENT.md</DocLink>.
        </p>
      </Section>

      <Section title="Locked out / lost the admin password">
        <p>
          There's no self-service "forgot password" in this UI, deliberately -- a tool holding SSH keys and Borg
          passphrases shouldn't accept an unauthenticated request as proof of identity. Reset it from the host or
          container instead:
        </p>
        <Code>docker compose exec backend python scripts/reset_password.py &lt;username&gt;{'\n'}docker compose exec backend python scripts/reset_password.py &lt;username&gt; --generate</Code>
        <p>
          The <code>--generate</code> form prints a strong random password once -- save it immediately, it can't be
          shown again. To add a second admin instead of resetting one, use{' '}
          <code>scripts/create_user.py &lt;username&gt;</code> the same way.
        </p>
      </Section>

      <Section title="Security notes">
        <p>
          SSH private keys and Borg passphrases are encrypted at rest, but that protects a stolen copy of the
          database file, not a compromised running instance -- this is a config-management tool, not a secrets
          vault. Full detail, including SSH host-key verification defaults and how to harden them, in{' '}
          <DocLink href={`${DOCS}/SECURITY.md`}>SECURITY.md</DocLink>.
        </p>
      </Section>

      <Section title="Full documentation">
        <ul className="list-disc space-y-1 pl-5">
          <li><DocLink href={`${DOCS}/ARCHITECTURE.md`}>ARCHITECTURE.md</DocLink> -- how monitoring, retention, and remote triggering reach your infrastructure</li>
          <li><DocLink href={`${DOCS}/DEPLOYMENT.md`}>DEPLOYMENT.md</DocLink> -- setup, updating, environment variables</li>
          <li><DocLink href={`${DOCS}/BACKUP.md`}>BACKUP.md</DocLink> -- backing up the portal's own database and secrets</li>
          <li><DocLink href={`${DOCS}/BORGMATIC_INTEGRATION.md`}>BORGMATIC_INTEGRATION.md</DocLink> -- coexisting with existing borgmatic clients</li>
          <li><DocLink href={`${DOCS}/BORG_COMPATIBILITY.md`}>BORG_COMPATIBILITY.md</DocLink> -- verify against your Borg version</li>
          <li><DocLink href={`${DOCS}/SECURITY.md`}>SECURITY.md</DocLink> -- encryption, login, host-key verification</li>
          <li><DocLink href={`${REPO}/blob/master/CHANGELOG.md`}>CHANGELOG.md</DocLink> -- release history</li>
        </ul>
      </Section>
    </div>
  )
}
