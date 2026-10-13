@python
Feature: guard-databases
  The guard for stored data: SQL or NoSQL drops, unbounded deletes, migration
  resets and restores. It rides in a quoted argument or a file, so it needs a
  SQL-level scan beyond the shell scanner. It is a stub today: it is not
  registered and judges nothing yet.

  Scenarios tagged @planned are verdicts no guard gives yet: they are
  expected to fail, so they never fail CI, and a row that starts passing
  shows as XPASS. The verdicts there are proposals, not rulings. Every
  scenario here is planned while the guard is a stub.

  # An allow row, written ahead: until the guard is registered the runner
  # denies every call to it (no guard is named so), so it is @planned too.
  # Drop the tag when the guard is registered.
  @planned
  Scenario Outline: reading or inserting stored data is allowed
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                              | note                          |
      | psql -c "SELECT id FROM users WHERE id = 7"          | a read                        |
      | psql -c "INSERT INTO users (name) VALUES ('ada')"    | adds, never erases            |
      | mongosh --eval 'db.users.find({})'                   | a read                        |
      | echo "DROP TABLE users is not something to run"      | prose                         |

  @planned
  Scenario Outline: a SQL or NoSQL drop is asked about
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                              | verdict | note                         |
      | psql -c "DROP TABLE users"                           | asks    |                              |
      | psql -c "DROP DATABASE app"                          | asks    |                              |
      | mysql -e "TRUNCATE TABLE sessions"                   | asks    |                              |
      | mongosh --eval 'db.users.drop()'                     | asks    | NoSQL                        |
      | mongosh --eval 'db.dropDatabase()'                   | asks    |                              |
      | redis-cli FLUSHALL                                   | asks    |                              |

  @planned
  Scenario Outline: a delete or update with no row limit is asked about
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                              | verdict | note                         |
      | psql -c "DELETE FROM users"                          | asks    | no WHERE                     |
      | sqlite3 app.db "UPDATE users SET active = 0"         | asks    | no WHERE                     |
      | mongosh --eval 'db.users.deleteMany({})'             | asks    | an empty filter              |

  @planned
  Scenario Outline: a migration reset or a restore is asked about
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                              | verdict | note                         |
      | rails db:reset                                       | asks    |                              |
      | rails db:drop                                        | asks    |                              |
      | npx prisma migrate reset --force                     | asks    |                              |
      | pg_restore --clean -d app dump.tar                   | asks    | overwrites what is there     |
      | psql app < dump.sql                                  | asks    | a restore                    |
