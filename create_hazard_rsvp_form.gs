/**
 * Creates the Hazard Family Reunion meal RSVP Google Form, links it to a
 * response spreadsheet, and adds a live meal-headcount summary tab.
 *
 * Run createHazardMealRsvp() once from https://script.new.
 */
function createHazardMealRsvp() {
  const title = 'Hazard Family Reunion — Group Meal RSVP';
  const form = FormApp.create(title, true);

  form
    .setDescription(
      'Please submit one response per household. Enter the number of adults ' +
      'and children attending each group meal. Select 0 for meals your household ' +
      'will skip. Use the Edit your response link after submitting if plans change.'
    )
    .setConfirmationMessage(
      'Thanks! Your meal counts were recorded. Save the “Edit your response” link ' +
      'shown below in case your plans change.'
    )
    .setAllowResponseEdits(true)
    .setCollectEmail(false)
    .setLimitOneResponsePerUser(false)
    .setProgressBar(true)
    .setPublishingSummary(false)
    .setShowLinkToRespondAgain(false)
    .setShuffleQuestions(false);

  form.addTextItem()
    .setTitle('Family / household name')
    .setRequired(true);

  form.addTextItem()
    .setTitle('Contact phone or email')
    .setHelpText('Optional; useful if the organizer has a meal question.')
    .setRequired(false);

  const countChoices = Array.from({length: 21}, (_, i) => String(i));
  const meals = [
    'Sunday, Aug. 2 — 3:00 PM lunch/dinner at Great Horned Owl Campground',
    'Monday, Aug. 3 — dinner at Great Horned Owl Campground',
    'Tuesday, Aug. 4 — lunch at North Park by the Provo Recreation Center',
    'Wednesday, Aug. 5 — dinner at Great Horned Owl Campground',
    'Thursday, Aug. 6 — dinner and dance at the Montana Avenue backyard',
    'Friday, Aug. 7 — dinner at Great Horned Owl Campground'
  ];

  meals.forEach((meal) => {
    form.addSectionHeaderItem().setTitle(meal);
    form.addListItem()
      .setTitle('Adults attending')
      .setChoiceValues(countChoices)
      .setRequired(true);
    form.addListItem()
      .setTitle('Children attending')
      .setChoiceValues(countChoices)
      .setRequired(true);
  });

  form.addParagraphTextItem()
    .setTitle('Dietary restrictions, allergies, or meal notes')
    .setRequired(false);

  const spreadsheet = SpreadsheetApp.create(title + ' — Responses');
  const totalsSheet = spreadsheet.getSheets()[0];
  totalsSheet.setName('Meal Totals');

  form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheet.getId());
  SpreadsheetApp.flush();

  // The linked response sheet is created asynchronously. Wait briefly for it.
  let responseSheet = null;
  for (let attempt = 0; attempt < 20 && !responseSheet; attempt += 1) {
    Utilities.sleep(500);
    responseSheet = spreadsheet.getSheets().find(
      (sheet) => sheet.getSheetId() !== totalsSheet.getSheetId()
    ) || null;
  }
  if (!responseSheet) {
    throw new Error(
      'The form was created, but the response sheet was not ready. Open the ' +
      'spreadsheet and add the totals formulas from the itinerary manually.'
    );
  }

  const responseTab = responseSheet.getName().replace(/'/g, "''");
  const responseRef = "'" + responseTab + "'!";
  const sumColumn = (column) =>
    '=SUM(ARRAYFORMULA(IFERROR(VALUE(' + responseRef + column + '2:' + column + '),0)))';

  totalsSheet.getRange('A1:D7').setValues([
    ['Group meal', 'Adults', 'Children', 'Total'],
    ['Sunday camp lunch/dinner', '', '', ''],
    ['Monday camp dinner', '', '', ''],
    ['Tuesday North Park lunch', '', '', ''],
    ['Wednesday camp dinner', '', '', ''],
    ['Thursday backyard dinner', '', '', ''],
    ['Friday camp dinner', '', '', '']
  ]);

  // Form response columns: A timestamp, B household, C contact,
  // then adult/child pairs in D:O, with dietary notes in P.
  const responseColumns = [
    ['D', 'E'], ['F', 'G'], ['H', 'I'],
    ['J', 'K'], ['L', 'M'], ['N', 'O']
  ];
  responseColumns.forEach(([adultColumn, childColumn], index) => {
    const row = index + 2;
    totalsSheet.getRange(row, 2).setFormula(sumColumn(adultColumn));
    totalsSheet.getRange(row, 3).setFormula(sumColumn(childColumn));
    totalsSheet.getRange(row, 4).setFormula('=SUM(B' + row + ':C' + row + ')');
  });

  totalsSheet.getRange('A9:B13').setValues([
    ['Organizer links', ''],
    ['Households responding', ''],
    ['Public RSVP form', form.getPublishedUrl()],
    ['Edit the form', form.getEditUrl()],
    ['Response spreadsheet', spreadsheet.getUrl()]
  ]);
  totalsSheet.getRange('B10').setFormula(
    '=COUNTA(' + responseRef + 'B2:B)'
  );

  totalsSheet.getRange('A1:D1').setFontWeight('bold');
  totalsSheet.getRange('A9:B9').setFontWeight('bold');
  totalsSheet.setFrozenRows(1);
  totalsSheet.autoResizeColumns(1, 4);
  totalsSheet.setColumnWidth(1, 260);
  totalsSheet.setColumnWidth(2, 420);

  const result = [
    'RSVP form: ' + form.getPublishedUrl(),
    'Edit form: ' + form.getEditUrl(),
    'Responses and totals: ' + spreadsheet.getUrl(),
    '',
    'Paste this into config.js:',
    "window.REUNION_CONFIG = { rsvpFormUrl: '" + form.getPublishedUrl() + "' };"
  ].join('\n');

  console.log(result);
  Logger.log(result);
  return result;
}
