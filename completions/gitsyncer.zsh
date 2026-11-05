# Loaded after compinit; no changes to global completion styles.
_gitsyncer() {
    local -a commands repos
    commands=(
      'status:List repositories and manage registrations'
      'add:Register a repository path'
      'remove:Remove a repository registration'
      'pull:Fetch and fast-forward pull'
      'push:Enter a message, then commit and push'
    )
    if (( CURRENT == 2 )); then
        _describe 'gitsyncer commands' commands
        return
    fi
    case "$words[2]" in
      add) _directories ;;
      pull|push)
        repos=(all "${(@f)$("$words[1]" _names 2>/dev/null)}")
        compadd -a repos ;;
      remove)
        repos=("${(@f)$("$words[1]" _names 2>/dev/null)}")
        compadd -a repos ;;
      status)
        if (( CURRENT == 3 )); then
            compadd -- add remove --no-interactive
        elif [[ "$words[3]" == add ]]; then
            _directories
        elif [[ "$words[3]" == remove ]]; then
            repos=("${(@f)$("$words[1]" _names 2>/dev/null)}")
            compadd -a repos
        fi ;;
    esac
}
compdef _gitsyncer gitsyncer 깃싱커
