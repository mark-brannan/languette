@python @family
Feature: stop
  The family of guards for a live thing that stops. A family is a
  configuration key that groups guards; this file holds the verdicts the
  family gives, run against every guard together.

  Scenarios tagged @planned are verdicts no guard gives yet: they are
  expected to fail, so they never fail CI, and a row that starts passing
  shows as XPASS. The verdicts there are proposals, not rulings. Every other
  scenario is allowed by design and fails CI when a guard stops allowing it.

  Scenario Outline: stopping the agent's own processes, units and dev containers is allowed
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                   | note                          |
      | pkill -f "vite --port 5173"               | the agent's dev server        |
      | systemctl --user stop dev-watch.service   | the user's own manager        |
      | docker compose down                       | a dev stack                   |
      | supabase stop                             | the local stack, data kept    |
      | nginx -s reload                           | a reload, not a stop          |
      | kubectl get nodes                         | a read                        |
      | gh run list --workflow ci.yml             | a read                        |
      | echo "kubectl drain node-1 is a maintenance step" | prose                 |

  @planned
  Scenario Outline: a CI run or workflow is stopped
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                      | verdict | note |
      | gh run cancel 4242                           | asks    |      |
      | gh workflow disable deploy.yml               | asks    | nothing runs it until it is re-enabled |

  @planned
  Scenario Outline: a cluster's workloads are drained or scaled away
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                  | verdict | note |
      | kubectl drain node-1 --ignore-daemonsets                 | asks    |      |
      | kubectl cordon node-2                                    | asks    |      |
      | kubectl scale deployment/web --replicas=0 -n prod        | asks    |      |
      | kubectl taint nodes node-1 maint=true:NoExecute          | asks    | evicts what runs there |

  @planned
  Scenario Outline: a deployed app or its platform stops
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                      | verdict | note |
      | kamal app stop -d production                 | asks    |      |
      | kamal accessory stop db                      | asks    |      |
      | kamal proxy stop                             | asks    | every app behind it |
      | modal app stop ap-orders                     | asks    |      |
      | modal container stop ta-01abc                | asks    |      |
      | railway down --yes                           | asks    |      |
      | curl -X POST https://backboard.railway.app/graphql/v2 -d '{"query":"mutation { deploymentRemove(id: \"d1\") }"}' | asks | |
      | supabase stop --no-backup                    | asks    | the local data goes too |
      | redis-cli -h prod-cache DEBUG SLEEP 30       | asks    | blocks every client |
      | redis-cli -h prod-cache DEBUG SEGFAULT       | asks    |      |
      | split splits kill checkout-v2 -e production  | asks    | all traffic falls back |

  @planned
  Scenario Outline: a load balancer on another host stops serving
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                   | verdict | note |
      | ssh web1 sudo nginx -s stop                               | asks    |      |
      | ssh web1 sudo nginx -s quit                               | asks    |      |
      | ssh web1 sudo service nginx stop                          | asks    |      |
      | ssh lb1 sudo systemctl stop haproxy                       | asks    |      |
      | ssh lb1 'echo "shutdown sessions server web/w1" \| socat stdio /run/haproxy.sock' | asks | |
      | ssh lb1 sudo kill -USR1 $(pidof haproxy)                  | asks    | a soft stop |
      | ssh edge1 docker stop traefik                             | asks    |      |
      | ssh edge1 sudo systemctl stop traefik                     | asks    |      |
      | ssh edge1 docker compose -f traefik.yml down              | asks    |      |
      | aws elbv2 deregister-targets --target-group-arn $TG --targets Id=i-0abc | asks | |
      | aws elb deregister-instances-from-load-balancer --load-balancer-name web --instances i-0abc | asks | |

  @planned
  Scenario Outline: the alerting that would report an outage is removed
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                   | verdict | note |
      | datadog-ci monitors delete 12345                          | asks    |      |
      | pd service delete -i PABC123                              | asks    |      |
      | pd schedule delete -i PSCHED1                             | asks    |      |
      | pd ep delete -i PESC1                                     | asks    | an escalation policy |
      | curl -X DELETE https://api.pagerduty.com/schedules/PSCHED1 | asks | |
      | curl -X DELETE https://api.pagerduty.com/services/PABC123 | asks | |
      | rm /etc/prometheus/rules/alerts.yml                       | asks    |      |
      | curl -X DELETE https://grafana.example.com/api/alert-notifications/3 | asks | |
      | newrelic synthetics monitor delete --guid MON1            | asks    |      |
