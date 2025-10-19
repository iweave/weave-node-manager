- Only ONE action per execution cycle (conservative approach).
    **Target:** Support multiple concurrent actions with configurable thresholds (e.g., max 2 upgrading, max 5 starting) in both single-shot and daemon modes. Single-shot mode remains default but can take multiple actions if thresholds allow.
    **Daemon mode:** Long-running process with REST API for JavaScript dashboard (opt-in).

- Nodes are added/removed based on the "youngest" (most recent `age` timestamp)
    **Target:** Pluggable selection strategies: youngest (default), least_records, most_banned, highest_cpu_load. Strategy pattern for easy A/B testing.

- Upgrades only proceed when no removals are pending
    **Keep:** Prevents runaway trimming when new versions consume more resources. Upgrades continue with fewer running nodes.
    **Decision:** Follow recommendation - keep this constraint.

- Database has single Machine row (id=1); updates apply to entire cluster
    **CORRECTION:** Each weave-node-manager instance manages ONE physical machine only. Nodes can run:
      - Directly on host OS (via systemd, setsid, antctl, launchctl)
      - Inside Docker containers on the same machine (single or multiple nodes per container)
    **Schema needs:** `Container` table (optional) for nodes running in containers, `Node.container_id` FK
    **Dashboard aggregation:** Separate concern - dashboard queries multiple wnm instances, but each wnm manages only its own machine.
    **No migrations needed:** Breaking DB changes OK, no users yet.

- Requires sudo access for systemd, ufw, file operations
    **HIGH PRIORITY:** Non-sudo operation preferred. Support multiple launch methods:
      - systemd (current, requires sudo)
      - systemd for user processes (non-sudo)
      - setsid (non-sudo, low resource)
      - antctl (official Autonomi manager)
      - launchctl (macOS)
      - docker (HIGH PRIORITY - run/monitor nodes IN containers)
    **Firewall:** Make optional/modular (ufw, firewalld, pf, none)
    **Import architectures from:** anm, antctl, formacio, Dimitar's docker methods
    **Migration strategy:** Only takeover anm, other's are manually managed so will not conflict with wnm

- Lock file prevents concurrent execution
    **Decision:** Keep file lock for single-shot mode (prevents overlapping cron runs). Use DB transactions for individual actions.
    **Action concurrency:** Sequential execution in single-shot (simple, safe), async in daemon mode (future).