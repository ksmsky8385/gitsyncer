_gitsyncer_complete() {
    local cur="${COMP_WORDS[COMP_CWORD]}" cmd="${COMP_WORDS[1]}" value expanded
    COMPREPLY=()
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W 'status add remove pull push --help --version' -- "$cur") )
    elif [[ "$cmd" == add || ( "$cmd" == status && "${COMP_WORDS[2]}" == add && $COMP_CWORD -eq 3 ) ]]; then
        compopt -o filenames
        expanded="$cur"
        [[ "$cur" == "~/"* ]] && expanded="$HOME/${cur:2}"
        [[ "$cur" == "~" ]] && expanded="$HOME/"
        while IFS= read -r value; do COMPREPLY+=("$value"); done < <(compgen -d -- "$expanded")
    elif [[ "$cmd" == pull || "$cmd" == push || "$cmd" == remove || ( "$cmd" == status && "${COMP_WORDS[2]}" == remove && $COMP_CWORD -eq 3 ) ]]; then
        if [[ "$cmd" == pull || "$cmd" == push ]]; then
            [[ all == "$cur"* ]] && COMPREPLY+=(all)
        fi
        while IFS= read -r value; do
            [[ -n "$value" && "$value" == "$cur"* ]] && COMPREPLY+=("$value")
        done < <("${COMP_WORDS[0]}" _names 2>/dev/null)
    elif [[ "$cmd" == status && $COMP_CWORD -eq 2 ]]; then
        COMPREPLY=( $(compgen -W 'add remove --no-interactive' -- "$cur") )
    fi
}
complete -F _gitsyncer_complete gitsyncer 깃싱커
# Show choices immediately on Tab for this command only.
_gitsyncer_menu_complete() {
    _gitsyncer_complete
    if [[ ${#COMPREPLY[@]} -gt 1 ]]; then
        printf '\n%s\n' "${COMPREPLY[@]}" >&2
    fi
}
complete -F _gitsyncer_menu_complete gitsyncer 깃싱커
