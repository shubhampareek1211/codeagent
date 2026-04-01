from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _read_json(path: Path) -> Any:
    with path.open('r', encoding='utf-8') as file:
        return json.load(file)


def load_knowledge_documents(knowledge_dir: str) -> List[Dict[str, Any]]:
    base = Path(knowledge_dir).resolve()

    profile = _read_json(base / 'profile.json')
    experiences = _read_json(base / 'experience.json')
    projects = _read_json(base / 'projects.json')
    education = _read_json(base / 'education.json')
    skills = _read_json(base / 'skills.json')
    faqs = _read_json(base / 'faqs.json')

    documents: List[Dict[str, Any]] = []

    documents.append(
        {
            'id': 'profile-core',
            'sourceType': 'profile',
            'title': 'Profile Summary',
            'content': '\n'.join(
                [
                    f"{profile['name']} — {profile['tagline']}",
                    profile['summary'],
                    f"Open to: {', '.join(profile.get('open_to', []))}",
                    f"Location: {profile.get('location', 'N/A')}",
                    f"Philosophy: {profile.get('philosophy', '')}",
                ]
            ),
            'metadata': profile,
        }
    )

    for experience in experiences:
        documents.append(
            {
                'id': f"experience-{experience['id']}",
                'sourceType': 'experience',
                'title': f"{experience['role']} @ {experience['company']}",
                'content': '\n'.join(
                    [
                        f"{experience['role']} at {experience['company']} ({experience['start']} - {experience['end']})",
                        f"Location: {experience.get('location', 'N/A')}",
                        f"Highlights: {' | '.join(experience.get('highlights', []))}",
                        f"Skills: {', '.join(experience.get('skills', []))}",
                        'Metrics: '
                        + ', '.join(
                            [f"{key}: {value}" for key, value in experience.get('metrics', {}).items()]
                        ),
                    ]
                ),
                'metadata': experience,
            }
        )

    for project in projects:
        documents.append(
            {
                'id': f"project-{project['id']}",
                'sourceType': 'project',
                'title': f"{project['name']} — {project['subtitle']}",
                'content': '\n'.join(
                    [
                        f"Category: {project.get('category', 'N/A')} | Status: {project.get('status', 'N/A')}",
                        f"Highlights: {' | '.join(project.get('highlights', []))}",
                        f"Tech: {', '.join(project.get('tech', []))}",
                        'Metrics: '
                        + ', '.join([f"{key}: {value}" for key, value in project.get('metrics', {}).items()]),
                    ]
                ),
                'metadata': project,
            }
        )

    for index, school in enumerate(education):
        documents.append(
            {
                'id': f'education-{index}',
                'sourceType': 'education',
                'title': f"{school['degree']} — {school['school']}",
                'content': '\n'.join(
                    [
                        f"{school['degree']} at {school['school']}",
                        f"Timeline: {school.get('start', 'N/A')} - {school.get('end', 'N/A')}",
                        f"Coursework: {', '.join(school.get('coursework', []))}" if school.get('coursework') else '',
                        f"Roles: {' | '.join(school.get('roles', []))}" if school.get('roles') else '',
                    ]
                ).strip(),
                'metadata': school,
            }
        )

    for group, items in skills.items():
        documents.append(
            {
                'id': f'skills-{group}',
                'sourceType': 'skills',
                'title': f'Skills — {group}',
                'content': f"{group}: {', '.join(items)}",
                'metadata': {'group': group, 'items': items},
            }
        )

    for faq in faqs:
        documents.append(
            {
                'id': f"faq-{faq['id']}",
                'sourceType': 'faq',
                'title': faq['question'],
                'content': faq['answer'],
                'metadata': faq,
            }
        )

    return documents
