<script lang="ts">
  // Settings → Your data → How to restore (0.9, D1): the steps of docs/restore.md, on screen,
  // for whoever looks after the server. backend/scripts/restore_test.sh follows the same steps
  // on a fresh container. Keep the two the same.
  import PageHeader from '#lib/components/PageHeader.svelte';
</script>

<PageHeader
  title="How to restore"
  parent={{ href: '/(app)/settings/your-data', label: 'Backups & your data' }}
/>

<div class="page">
  <p class="lead">
    These steps are for whoever looks after the server Mealwright runs on. Below, <code
      >&lt;folder&gt;</code
    >
    is the folder that holds <code>compose.yaml</code> and the <code>data</code> folder.
  </p>

  <section aria-labelledby="holds">
    <h2 id="holds">What a backup holds</h2>
    <ul>
      <li>
        <strong>The database:</strong> every recipe, plan, list, pantry item, person, login and
        setting, in one file: <code>data/backups/backup-&lt;date&gt;-&lt;time&gt;.db</code> (the time
        in UTC).
      </li>
      <li>
        <strong>The photos, when Include photos was on</strong> (it is, unless an admin switched it
        off): a folder beside the database file, named like it with <code>-photos</code> in place of
        <code>.db</code>, for example
        <code>data/backups/backup-&lt;date&gt;-&lt;time&gt;-photos</code>. A backup made with
        Include photos off, by an older version, or when there were no photos has none: restoring it
        keeps the photos already on the server, and a recipe whose photo file is missing shows no
        photo. Copy the data folder (or at least <code>backups</code> and
        <code>photos</code>) to another disk or your NAS as well. The folders are mostly links, so
        use <code>tar</code> or <code>restic</code>, or <code>rsync -aH</code>.
      </li>
      <li>
        <strong>Leave out <code>logs</code>.</strong> It holds the sign-in lines, which Mealwright
        keeps for 14 days only; a copy would keep them for longer. For example (<code
          >&lt;another disk&gt;</code
        >
        is where the copy goes):
        <pre><code
            >sudo tar -C &lt;folder&gt; --exclude=data/logs -czf "&lt;another disk&gt;/mealwright-data-$(date +%Y%m%d-%H%M).tar.gz" data</code
          ></pre>
        With&nbsp;<code>rsync</code>, add <code>--exclude=logs/</code>.
      </li>
      <li>
        The copies made before an upgrade (<code>pre-upgrade-…</code>) and before Delete everything
        (<code>before-delete-everything-…</code>) restore the same way, with their own photos
        folders.
      </li>
    </ul>
  </section>

  <section aria-labelledby="same">
    <h2 id="same">On the same server</h2>
    <ol>
      <li>
        Stop Mealwright, so nothing writes to the database while you swap it:
        <pre><code
            >cd &lt;folder&gt;
docker compose stop mealwright</code
          ></pre>
      </li>
      <li>
        Pick the backup. The newest is first. Pick a <code>backup-…</code> file (or a
        <code>before-delete-everything-…</code> one, to undo a Delete everything):
        <pre><code>sudo ls -lt data/backups/</code></pre>
      </li>
      <li>
        Keep the current database aside, with the two files beside it, then put the backup in its
        place:
        <pre><code
            >STAMP=$(date +%Y%m%d-%H%M)
sudo mkdir -p "data/before-restore-$STAMP"
sudo mv data/mealwright.db data/mealwright.db-wal data/mealwright.db-shm "data/before-restore-$STAMP/" 2&gt;/dev/null
sudo cp data/backups/backup-&lt;date&gt;-&lt;time&gt;.db data/mealwright.db
sudo chown 10001:10001 data/mealwright.db
sudo chmod 600 data/mealwright.db</code
          ></pre>
      </li>
      <li>
        Put the photos back, if the backup has a photos folder (the same name as the
        <code>.db</code> file you picked, with <code>-photos</code> in place of <code>.db</code>);
        skip this when there is none. It adds them to the photos already there:
        <pre><code
            >sudo mkdir -p data/photos
sudo cp -an data/backups/backup-&lt;date&gt;-&lt;time&gt;-photos/. data/photos/
sudo chown -R 10001:10001 data/photos</code
          ></pre>
      </li>
      <li>
        Start it, and check:
        <pre><code
            >docker compose up -d
docker compose logs -f</code
          ></pre>
        Sign in with the password you had when the backup was made. Everything is as it was then; whatever
        changed after it is gone. Once all is well, you can delete the
        <code>data/before-restore-…</code> folder.
      </li>
    </ol>
  </section>

  <section aria-labelledby="new">
    <h2 id="new">On a new server</h2>
    <ol>
      <li>Install Mealwright, the same version or a newer one, but don’t start it yet.</li>
      <li>
        Copy your copy of the data folder into <code>&lt;folder&gt;/data</code>. With only a backup
        file, put it there as <code>mealwright.db</code>, with the backup’s photos folder (or your
        own copy of <code>photos</code>) as <code>data/photos</code>.
      </li>
      <li>
        Give it to Mealwright’s user:
        <pre><code
            >sudo chown -R 10001:10001 &lt;folder&gt;/data
sudo chmod 600 &lt;folder&gt;/data/mealwright.db</code
          ></pre>
      </li>
      <li>
        Start it (<code>docker compose up -d</code>) and sign in. A backup from an older version is
        brought up to date when Mealwright starts; one from a newer version doesn’t open in an older
        one.
      </li>
    </ol>
  </section>

  <section aria-labelledby="wont">
    <h2 id="wont">If it doesn’t start</h2>
    <p>
      <code>docker compose logs</code> says why. Put the database you kept aside back (<code
        >data/before-restore-…/mealwright.db</code
      >) and start again.
    </p>
  </section>
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    max-width: 760px;
    color: var(--color-text);
    font-size: var(--text-lg);
    line-height: 1.5;
  }

  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  h2 {
    font-size: 1.0625rem;
    font-weight: var(--weight-extrabold);
  }

  .lead {
    color: var(--color-text-muted);
  }

  ul,
  ol {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    margin: 0;
    padding-left: 1.4em;
  }

  code {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.875em;
    overflow-wrap: anywhere;
  }

  pre {
    margin: var(--space-4) 0;
    padding: var(--space-6);
    border-radius: var(--radius-field);
    background: var(--color-surface);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
</style>
