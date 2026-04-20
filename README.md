# talks

Public home for talks, workshops, and conference sessions by **Shayon Sanyal** — Principal PostgreSQL Specialist Solutions Architect · Lead, Agentic AI for Databases at AWS.

Each talk lives under `conferences/<slug>/` with its own README, runnable code, slide deck, and anything else needed to reproduce it.

## Talks

| Venue                             | Date         | Title                                                            | Folder                                                                                               |
| --------------------------------- | ------------ | ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **PostgresConf 2026** · San Pedro | Apr 21, 2026 | Building Agentic AI Applications with PostgreSQL as the Backbone | [`conferences/2026-postgresconf-agentic-ai/`](conferences/2026-postgresconf-agentic-ai/) |

## Layout

```
talks/
├── README.md                                  # you are here
└── conferences/
    └── <year>-<venue>-<topic-slug>/
        ├── README.md                          # talk's README (abstract, demo script, run instructions)
        ├── deck/                              # Marp source + built PDF + theme
        │   ├── deck.md
        │   ├── deck.pdf
        │   └── theme.css
        ├── <code for the live demo>
        └── static/
```

## Recordings + slides

Where a talk has been recorded, the folder's README links to the video. Slide PDFs are built from `deck/deck.md` via [Marp](https://marp.app/) — run `./deck/build.sh` inside any talk folder to rebuild.

## Contact

- LinkedIn · [linkedin.com/in/shayonsanyal](https://www.linkedin.com/in/shayonsanyal/)
- GitHub · [@shayons](https://github.com/shayons)

If you'd like me to speak at your event, reach out on LinkedIn with a short description and date range.
