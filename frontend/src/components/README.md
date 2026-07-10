# `src/components/` — shared presentational components

Empty in Story 1.1, and named in the spine's source tree, so it exists now.

Components shared across two or more features live here; a component used by exactly one
feature lives with that feature until a second caller appears.

The spine explicitly defers the choice of styling approach and component library. Story
1.1 must not make that choice on 26 later stories' behalf, so `src/index.css` is plain
CSS and nothing here presumes otherwise.

React components are `PascalCase`; hooks are `useThing`.
