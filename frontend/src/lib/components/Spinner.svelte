<script lang="ts">
  // A small turning ring that says "working on it" during a long wait (F258, proposed, for
  // cabledrawer). It sits before words that say what is happening, inside a status region, so
  // screen readers hear only the words. It is as big as the text around it; with "less motion"
  // asked for, it stands still (base.css).
</script>

<span class="ring" data-spinner aria-hidden="true"></span>

<style>
  .ring {
    display: inline-block;
    flex: none;
    width: 1em;
    height: 1em;
    vertical-align: -0.125em;
    border: 0.15em solid var(--color-border-strong);
    border-top-color: var(--color-accent);
    border-radius: 50%;
    animation: turn 0.9s linear infinite;
  }

  @keyframes turn {
    to {
      transform: rotate(1turn);
    }
  }
</style>
