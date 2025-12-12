# Example: Architecture Review with Eval Framework

This example shows how to perform an architecture review that produces
comparable, structured output using the eval-framework.

## Request Format

When asking for a review, include the eval-framework directive:

```
Perform an architecture review of [path] using the eval-framework output format.
Focus on [criteria]. Save results to .eval-results/
```

## Example Request

```
Perform an architecture review of deployment/boot-manager/ using the
eval-framework output format. Focus on IoT production readiness including
thread safety, resource management, and error recovery. Save results to
.eval-results/
```

## Example Output

The evaluation should produce YAML output like this:

```yaml
---
evaluation:
  id: "eval-a1b2c3d4"
  type: "architecture-review"
  date: "2025-12-12T15:30:00Z"
  model: "claude-opus-4-5-20251101"

  target:
    path: "deployment/boot-manager/"
    commit: "34b5478"
    description: "Python boot manager for IoT Raspberry Pi devices"

  context:
    criteria: "IoT production readiness"
    scope: "full"
    time_spent_minutes: 45

findings:
  - id: "CRITICAL-001"
    severity: "critical"
    category: "thread-safety"

    location:
      file: "state/machine.py"
      line: 391
      function: "_notify_boot_callbacks"

    title: "Callbacks invoked inside lock causing potential deadlock"

    evidence: |
      def fire(self, trigger, **context):
          with self._lock:
              # ... state changes ...
              self._notify_boot_callbacks(old_state, self._boot_state, trigger)

      def _notify_boot_callbacks(self, old_state, new_state, trigger):
          for callback in self._boot_callbacks:
              callback(old_state, new_state, trigger)  # External code with lock held

    reasoning: |
      Callbacks are invoked while holding self._lock. This creates deadlock risk:
      1. Callbacks may block on I/O while holding lock
      2. Callbacks may call back into state machine (needs same lock)
      3. Callbacks may spawn threads that need the lock

      IoT systems run unattended for months. Even rare deadlocks are unacceptable
      because they require physical access to reset the device.

    impact: "Complete system hang during state transitions, requiring physical reset"

    recommendation: |
      Copy callback list inside lock, invoke callbacks outside lock:

      def _notify_boot_callbacks(self, old_state, new_state, trigger):
          with self._lock:
              callbacks = list(self._boot_callbacks)

          for callback in callbacks:
              try:
                  callback(old_state, new_state, trigger)
              except Exception:
                  pass

    fix_applied: false
    work_item: null

  - id: "CRITICAL-002"
    severity: "critical"
    category: "thread-safety"

    location:
      file: "container/manager.py"
      line: 88
      function: "__init__"

    title: "ContainerManager missing thread safety"

    evidence: |
      class ContainerManager:
          def __init__(self, config, state_machine=None):
              # No self._lock defined
              self._docker = DockerClient(config)
              self._initialized = False  # Accessed from multiple threads

    reasoning: |
      ContainerManager is accessed from multiple threads:
      - Main thread: lifecycle operations
      - Flask threads: API endpoints
      - Health monitor thread: callbacks

      Without locks, concurrent operations can interleave causing:
      - Torn reads in get_status()
      - Conflicting start/stop operations
      - Race conditions in initialization checks

    impact: "Incorrect container state reporting, conflicting operations"

    recommendation: |
      Add RLock to protect all public methods:

      def __init__(self, ...):
          self._lock = threading.RLock()
          # ...

      def get_status(self):
          with self._lock:
              # ... existing code ...

    fix_applied: false
    work_item: null

  # ... more findings ...

scores:
  categories:
    thread_safety: 5
    resource_management: 8
    error_handling: 7
    state_management: 7
    external_operations: 7
    api_web_layer: 8
    configuration: 9
    code_consistency: 7

  overall: 6.5
  production_ready: false

summary:
  total_findings: 15
  by_severity:
    critical: 5
    high: 5
    medium: 3
    low: 2
    info: 0

  top_issues:
    - "CRITICAL-001: Callbacks invoked inside lock"
    - "CRITICAL-002: ContainerManager missing thread safety"
    - "CRITICAL-003: HealthMonitor missing thread safety"
    - "CRITICAL-004: StatePersistence file descriptor leak"
    - "CRITICAL-005: UpdateManager TOCTOU race"

  positive_observations:
    - "Excellent separation of concerns between subsystems"
    - "Comprehensive logging with structured fields"
    - "Good use of Python typing throughout"
    - "Atomic file writes for persistence"

  fingerprint: "a1b2c3d4e5f6"
---
```

## Running Comparison

After running the review multiple times:

```bash
# Compare two reviews
python3 skills/eval-framework/scripts/compare-evaluations.py \
  .eval-results/arch-review-2025-12-12-eval-a1b2c3d4.yaml \
  .eval-results/arch-review-2025-12-12-eval-e5f6g7h8.yaml \
  --output .eval-results/comparison-2025-12-12.md
```

## Key Points for Reproducibility

1. **Be specific about scope** - "deployment/boot-manager/" not "the boot manager"
2. **State criteria explicitly** - "IoT production readiness" vs generic "review"
3. **Include commit hash** - Ensures same code version
4. **Use normalized categories** - From the schema, not ad-hoc
5. **Provide evidence** - Code snippets enable matching
6. **Explain reasoning** - Not just "this is bad" but *why*

## Interpretation

When comparing evaluations:

- **High overlap + high severity agreement** = Consistent, trustworthy results
- **Low overlap** = Investigate why findings differ
- **Same findings, different severity** = Calibration variance
- **Findings only in one** = Potential gaps in other evaluation
